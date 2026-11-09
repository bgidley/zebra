"""The dream cycle's Commons step (#235, S8): offers, imports, sharing promotion, report.

Runs ``commons_dream`` on a real engine with every registered action, a real library holding
the shipped *Commons Offer* / *Commons Import*, a real publisher and exchange over an in-memory
public relay and a local web of trust. Only the LLM and the metrics store are faked.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from importlib.metadata import entry_points
from pathlib import Path

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState
from zebra.definitions.loader import load_definition_from_yaml
from zebra.storage.memory import InMemoryStore
from zebra.tasks.registry import ActionRegistry
from zebra_tasks.commons import dream
from zebra_tasks.commons.dream import (
    DREAM_IMPORT_KEY,
    match_overlap,
    sharing_approvals,
    wait_for_imports,
)
from zebra_tasks.llm.base import LLMResponse, TokenUsage
from zebra_tasks.llm.client import set_llm_factory

from zebra_agent.commons import keys
from zebra_agent.commons.client import InMemoryCommonsClient, InMemoryRelay
from zebra_agent.commons.exchange import CommonsExchange
from zebra_agent.commons.identity import make_device_cert
from zebra_agent.commons.kinds import OFFER_KIND
from zebra_agent.commons.mirror import InMemoryCommonsMirror
from zebra_agent.commons.offer import offer_content
from zebra_agent.commons.offers import JUDGING, SEEN, InMemoryOfferStore
from zebra_agent.commons.peers import InMemoryTrustStore as InMemoryPeerStore
from zebra_agent.commons.publisher import CommonsPublisher
from zebra_agent.commons.sync import APPROVED, DECLINED, record_share, share_records
from zebra_agent.commons.web_of_trust import WebOfTrust
from zebra_agent.library import WorkflowLibrary
from zebra_agent.metrics import WorkflowStats
from zebra_agent.storage.trust import InMemoryTrustStore, TrustLevel

BUILTIN = Path(__file__).resolve().parents[1] / "workflows"
OWNER = 1

DREAM_STEP = """
name: Dream Step
first_task_id: commons
tasks:
  commons:
    name: Commons
    action: commons_dream
    properties:
      capability_gaps: "{{gaps}}"
      output_key: commons
routings: []
"""


def _workflow(name: str, description: str = "Answer questions about capital cities") -> str:
    return f"""name: "{name}"
description: "{description}"
tags: [facts]
version: 1
first_task: answer
tasks:
  answer:
    name: "Answer"
    action: llm_call
    properties:
      prompt: "Answer: {{{{goal}}}}"
      output_key: answer
"""


class FakeLLM:
    """Every LLM call of the offer and import pipelines, told apart by the system prompt."""

    model = "fake"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def complete(self, messages, **kwargs) -> LLMResponse:
        system = messages[0].content if messages and messages[0].role == "system" else ""
        if "public listing" in system:
            kind = "listing"
            content = json.dumps(
                {
                    "summary": "Answers capital-city questions; every run here worked.",
                    "use_when": "Someone asks for a capital city",
                    "golden_tasks": [
                        {
                            "goal": "What is the capital of Australia?",
                            "expected": "Canberra",
                            "criteria": ["Names Canberra"],
                        }
                    ],
                }
            )
        elif "Find personal data" in system:
            kind, content = "pii", '{"personal_data": false, "findings": []}'
        elif "grade the output" in system:
            kind = "judge"
            content = json.dumps({"criteria": [{"criterion": 1, "score": 1}], "reasoning": "ok"})
        elif "Kant" in system or "ethic" in system.lower():
            kind = "ethics"
            content = json.dumps({"approved": True, "overall_reasoning": "Fine.", "concerns": []})
        else:
            kind, content = "other", "Canberra"
        self.calls.append(kind)
        return LLMResponse(
            content=content,
            tool_calls=None,
            finish_reason="stop",
            usage=TokenUsage(input_tokens=10, output_tokens=5),
            model=self.model,
        )


class Metrics:
    """Per-workflow stats and a fixed ledger spend per dream-started import tree."""

    def __init__(self) -> None:
        self.stats: dict[str, WorkflowStats] = {}
        self.spend: float | None = 0.0
        self.raise_on_stats = False

    def good(self, name: str, runs: int = 6, ok: int | None = None, rating: float | None = 5.0):
        self.stats[name] = WorkflowStats(
            name, total_runs=runs, successful_runs=runs if ok is None else ok, avg_rating=rating
        )

    async def get_stats(self, name: str) -> WorkflowStats:
        if self.raise_on_stats:
            raise RuntimeError("metrics store down")
        return self.stats.get(name, WorkflowStats(name))

    async def get_spend_for_processes(self, process_ids):
        return None if self.spend is None else (self.spend, 0, 0)


class Commons:
    def __init__(self, reason: str | None = None) -> None:
        self.reason = reason

    async def stop_reason(self) -> str | None:
        return self.reason

    async def held_events(self) -> list:
        return []


def _zebra() -> dict:
    zebra_secret, device_secret = keys.generate_secret_key(), keys.generate_secret_key()
    cert = make_device_cert(
        zebra_secret, keys.public_key(device_secret), label="Home", sphere="home", observed=False
    )
    return {"zebra": keys.public_key(zebra_secret), "device": device_secret, "cert": cert}


def _publisher(z: dict, relay: InMemoryRelay) -> CommonsPublisher:
    return CommonsPublisher(
        canonical=InMemoryCommonsClient(relay),
        device_secret=z["device"],
        zebra_pubkey=z["zebra"],
        mirror=InMemoryCommonsMirror(),
        certs=[z["cert"]],
        receipt_wait=0,
    )


@pytest.fixture
def llm() -> FakeLLM:
    fake = FakeLLM()
    set_llm_factory(lambda model: fake)
    return fake


@pytest.fixture
async def world(tmp_path, llm):
    relay = InMemoryRelay(private=False)
    me = _zebra()
    publisher = _publisher(me, relay)
    web = WebOfTrust(InMemoryPeerStore(), me["zebra"])
    exchange = CommonsExchange(publisher=publisher, offers=InMemoryOfferStore(), trust=web)
    other = CommonsExchange(publisher=_publisher(_zebra(), relay), offers=InMemoryOfferStore())
    metrics = Metrics()
    golden = tmp_path / "golden"
    golden.mkdir()
    library = WorkflowLibrary(
        tmp_path / "library", metrics, owner_user_id=OWNER, sphere="home", device="home",
        golden_path=golden,
    )  # fmt: skip
    library.ensure_initialized()
    library.copy_builtin_workflows(BUILTIN)
    registry = ActionRegistry()
    registry.register_defaults()
    for ep in entry_points(group="zebra.tasks"):
        registry.register_action(ep.name, ep.load())
    trust = InMemoryTrustStore()
    extras = {
        "__workflow_library__": library,
        "__metrics_store__": metrics,
        "__commons__": Commons(),
        "__commons_publisher__": publisher,
        "__commons_exchange__": exchange,
        "__trust_store__": trust,
    }
    engine = WorkflowEngine(InMemoryStore(), registry, extras=extras)
    w = type("World", (), {})()
    w.relay, w.exchange, w.other, w.metrics, w.library = relay, exchange, other, metrics, library
    w.engine, w.trust, w.web, w.extras, w.publisher = engine, trust, web, extras, publisher
    yield w
    await wait_for_imports()


async def _dream(w, gaps: list | None = None, **settings) -> dict:
    definition = load_definition_from_yaml(DREAM_STEP)
    definition.tasks["commons"].properties.update(settings)
    process = await w.engine.create_process(definition, properties={"gaps": gaps or []})
    await w.engine.start_process(process.id)
    process = await w.engine.store.load_process(process.id)
    assert process.state == ProcessState.COMPLETE  # the step never fails the cycle
    return process.properties["commons"]


async def _publish_other(w, name: str, summary: str, use_when: str) -> str:
    content = offer_content(
        name=name,
        summary=summary,
        use_when=use_when,
        stats={"runs": 8, "success_rate": 1.0, "avg_rating": 4.5, "gym_score": 0.9},
        actions=["llm_call"],
        golden_tasks=[{"goal": "Plan a trip", "expected": "A plan", "criteria": ["Has a plan"]}],
        yaml=_workflow(name, summary),
    )
    published = await w.other.publisher.publish_offer(content, None)
    await w.exchange.poll()
    return published["content_sha256"]


def _gap_workflow(w, name="Weekend Trip Itinerary", text="Plan a weekend trip itinerary"):
    """The creator wrote this because the selector found no good workflow: a gap."""
    w.library.save(_workflow(name, text), writer="creator")


async def _processes(w, workflow: str) -> list:
    definition = w.library.get_workflow(workflow)
    return await w.engine.store.list_processes(definition_id=definition.id, include_completed=True)


# -- off by default ----------------------------------------------------------------------------


async def test_no_publisher_is_commons_off(world, llm):
    del world.extras["__commons_publisher__"]
    world.library.save(_workflow("Capital Facts"), writer="human")
    world.metrics.good("Capital Facts")

    report = await _dream(world)

    assert report["status"] == "off"
    assert report["voice_text"].startswith("Commons off")
    assert await _processes(world, "Commons Offer") == []
    assert llm.calls == []
    assert world.relay.events == []


async def test_disabled_setting_is_off(world, monkeypatch):
    monkeypatch.setenv("ZEBRA_COMMONS_DREAM_ENABLED", "false")
    world.library.save(_workflow("Capital Facts"), writer="human")
    world.metrics.good("Capital Facts")

    report = await _dream(world)

    assert report["status"] == "off"
    assert await _processes(world, "Commons Offer") == []


async def test_stopped_commons_does_nothing(world):
    world.extras["__commons__"] = Commons("kill switch on")
    world.library.save(_workflow("Capital Facts"), writer="human")
    world.metrics.good("Capital Facts")

    report = await _dream(world)

    assert report["status"] == "stopped"
    assert "kill switch on" in report["voice_text"]
    assert await _processes(world, "Commons Offer") == []


async def test_an_unexpected_error_never_fails_the_cycle(world, monkeypatch):
    async def boom():
        raise RuntimeError("owner lookup broke")

    monkeypatch.setattr(world.library, "refresh_owner", boom)

    report = await _dream(world)

    assert report["status"] == "error"
    assert "owner lookup broke" in report["errors"][0]


async def test_a_failing_part_is_reported_and_the_rest_runs(world):
    world.library.save(_workflow("Capital Facts"), writer="human")
    world.metrics.raise_on_stats = True

    report = await _dream(world)

    assert report["status"] == "ran"
    assert any("metrics store down" in e for e in report["errors"])


# -- offers ------------------------------------------------------------------------------------


async def test_good_learnt_workflow_gets_one_offer_waiting_on_the_owner(world):
    """E2E: the offer proposal appears as a human task; nothing is published or approved."""
    world.library.save(_workflow("Capital Facts"), writer="human")
    world.metrics.good("Capital Facts")

    report = await _dream(world)

    [offer] = report["offers_proposed"]
    assert (offer["name"], offer["kind"], offer["outcome"]) == (
        "Capital Facts",
        "suggest",
        "waiting",
    )
    pending = await world.engine.get_pending_tasks(offer["process_id"])
    assert [t.task_definition_id for t in pending] == ["owner_approval"]
    assert "public" not in world.library.commons_block("Capital Facts")["share_with"]
    assert [e for e in world.relay.events if e.kind == OFFER_KIND] == []
    assert "I asked you whether to offer Capital Facts" in report["voice_text"]
    statuses = [r["status"] for r in share_records(world.library) if r["sphere"] == "public"]
    assert statuses == ["proposed"]

    # The next cycle does not ask again while the offer is open (nor for this version).
    again = await _dream(world)
    assert again["offers_proposed"] == []
    assert len(await _processes(world, "Commons Offer")) == 1
    waiting = "an offer of it is already waiting for an answer"
    assert {"kind": "offer", "name": "Capital Facts", "reason": waiting} in again["skipped"]


async def test_public_already_shared_starts_the_publish(world):
    world.library.save(_workflow("Capital Facts"), writer="human")
    world.metrics.good("Capital Facts")
    digest = world.library.commons_block("Capital Facts")["content_sha256"]
    assert world.library.approve_share("Capital Facts", "public", digest)

    report = await _dream(world)

    [offer] = report["offers_proposed"]
    assert offer["kind"] == "publish"
    assert "You'd already agreed to share Capital Facts publicly" in report["voice_text"]


@pytest.mark.parametrize(
    ("runs", "ok", "rating", "reason"),
    [
        (6, 4, 5.0, "success rate 67% < 80%"),
        (6, 6, 3.0, "average rating 3.0 < 4.0"),
    ],
)
async def test_poor_stats_are_skipped_with_a_reason(world, runs, ok, rating, reason):
    world.library.save(_workflow("Capital Facts"), writer="human")
    world.metrics.good("Capital Facts", runs=runs, ok=ok, rating=rating)

    report = await _dream(world)

    assert report["offers_proposed"] == []
    assert {"kind": "offer", "name": "Capital Facts", "reason": reason} in report["skipped"]


async def test_unrated_workflow_with_good_success_rate_is_offered(world):
    world.library.save(_workflow("Capital Facts"), writer="human")
    world.metrics.good("Capital Facts", rating=None)

    report = await _dream(world)

    assert [o["name"] for o in report["offers_proposed"]] == ["Capital Facts"]


async def test_too_few_runs_builtins_and_system_workflows_are_never_candidates(world):
    world.library.save(_workflow("Capital Facts"), writer="human")
    world.metrics.good("Capital Facts", runs=4)
    for info in await world.library.list_workflows():
        if info.name != "Capital Facts":
            world.metrics.good(info.name)  # shipped built-ins and system workflows

    report = await _dream(world)

    assert report["offers_proposed"] == []  # built-ins (shipped) and system workflows skipped
    assert await _processes(world, "Commons Offer") == []


async def test_leak_tainted_workflow_is_skipped(world):
    world.library.save(_workflow("Capital Facts"), writer="optimizer", leak={"status": "kept"})
    world.metrics.good("Capital Facts")

    report = await _dream(world)

    assert report["offers_proposed"] == []
    [skip] = [s for s in report["skipped"] if s["name"] == "Capital Facts"]
    assert "leak guard" in skip["reason"]


async def test_offers_are_capped_per_cycle(world):
    world.library.save(_workflow("Capital Facts"), writer="human")
    world.library.save(_workflow("River Facts", "Answer questions about rivers"), writer="human")
    world.metrics.good("Capital Facts", rating=5.0)
    world.metrics.good("River Facts", rating=4.5)

    report = await _dream(world)

    assert [o["name"] for o in report["offers_proposed"]] == ["Capital Facts"]
    assert {"kind": "offer", "name": "River Facts",
            "reason": "over this cycle's cap of 1 offer(s)"} in report["skipped"]  # fmt: skip
    assert len(await _processes(world, "Commons Offer")) == 1


async def test_an_offer_that_stops_is_reported_not_proposed(world, llm, monkeypatch):
    world.library.save(_workflow("Capital Facts"), writer="human")
    world.metrics.good("Capital Facts")

    async def broken(*args, **kwargs):
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(llm, "complete", broken)

    report = await _dream(world)

    assert report["offers_proposed"] == []
    [skip] = [s for s in report["skipped"] if s["name"] == "Capital Facts"]
    assert skip["reason"].startswith("the offer stopped: could not write an honest summary")


async def test_an_offer_that_cannot_start_may_be_asked_again(world, monkeypatch):
    world.library.save(_workflow("Capital Facts"), writer="human")
    world.metrics.good("Capital Facts")

    async def refuse(*args, **kwargs):
        raise RuntimeError("launch refused")

    monkeypatch.setattr("zebra_tasks.launch.create_library_process", refuse)

    report = await _dream(world)

    assert report["offers_proposed"] == []
    assert any("launch refused" in e for e in report["errors"])
    statuses = [r["status"] for r in share_records(world.library) if r["sphere"] == "public"]
    assert statuses == ["proposed", "failed"]  # failed is not a decision

    monkeypatch.undo()
    again = await _dream(world)
    assert [o["name"] for o in again["offers_proposed"]] == ["Capital Facts"]


# -- imports -----------------------------------------------------------------------------------


def test_match_overlap_uses_the_memory_keywords():
    assert match_overlap("Plan a weekend trip itinerary", "Trip Planner: a weekend itinerary") == 3
    assert match_overlap("Plan a weekend trip itinerary", "Capital cities") == 0
    assert match_overlap("", "anything") == 0


async def test_trusted_matching_offer_starts_one_import(world):
    """E2E: a capability gap and a trusted matching offer → an import is started."""
    sha = await _publish_other(
        world, "Trip Planner", "Builds a weekend trip itinerary", "Planning a trip itinerary"
    )
    await world.web.vouch(world.other.zebra_pubkey)  # local trust 0.8 → score 0.56
    _gap_workflow(world)

    report = await _dream(world)

    [started] = report["imports_started"]
    assert started["content_sha256"] == sha
    assert started["score"] == pytest.approx(0.56)
    assert started["gap"] == "Weekend Trip Itinerary" and started["gap_source"] == "selector"
    assert (await world.exchange.offers.get(sha)).status != SEEN  # judging (or judged)
    [process] = await _processes(world, "Commons Import")
    assert process.id == started["process_id"]
    assert process.properties[DREAM_IMPORT_KEY] is True
    assert "I'm trying Trip Planner" in report["voice_text"]
    await wait_for_imports()


async def test_untrusted_matching_offer_is_skipped_with_its_score(world):
    sha = await _publish_other(
        world, "Trip Planner", "Builds a weekend trip itinerary", "Planning a trip itinerary"
    )
    _gap_workflow(world)

    report = await _dream(world)

    assert report["imports_started"] == []
    assert {"kind": "import", "name": "Trip Planner",
            "reason": "import score 0.00 < 0.50"} in report["skipped"]  # fmt: skip
    assert "don't trust its publisher enough" in report["voice_text"]
    assert (await world.exchange.offers.get(sha)).status == SEEN
    assert await _processes(world, "Commons Import") == []


async def test_continuation_gaps_match_too(world):
    await _publish_other(
        world, "Invoice Chaser", "Chases unpaid invoices by email", "Unpaid invoices"
    )
    await world.web.vouch(world.other.zebra_pubkey)
    gaps = [{"comment": "now chase the unpaid invoices", "rationale": "needs invoice chasing"}]

    report = await _dream(world, gaps=gaps)

    [started] = report["imports_started"]
    assert started["gap_source"] == "continuation"


async def test_non_matching_offers_are_left_alone(world):
    await _publish_other(world, "Recipe Box", "Suggests dinner recipes", "Cooking dinner")
    await world.web.vouch(world.other.zebra_pubkey)
    _gap_workflow(world)

    report = await _dream(world)

    assert report["imports_started"] == [] and report["skipped"] == []


async def test_imports_are_capped_per_cycle(world):
    await _publish_other(world, "Trip Planner", "Weekend trip itinerary", "Trip itinerary")
    await _publish_other(world, "Trip Helper", "Weekend trip itinerary helper", "Trip itinerary")
    await world.web.vouch(world.other.zebra_pubkey)
    _gap_workflow(world)

    report = await _dream(world)

    assert len(report["imports_started"]) == 1
    assert [s["reason"] for s in report["skipped"] if s["kind"] == "import"] == [
        "over this cycle's cap of 1 import(s)"
    ]


async def test_no_import_once_the_daily_budget_is_spent(world):
    await _publish_other(world, "Trip Planner", "Weekend trip itinerary", "Trip itinerary")
    await world.web.vouch(world.other.zebra_pubkey)
    _gap_workflow(world)
    # An import the dream cycle started earlier today, which spent $0.60 (ledger)
    await world.engine.create_process(
        world.library.get_workflow("Commons Import"), properties={DREAM_IMPORT_KEY: True}
    )
    world.metrics.spend = 0.6

    report = await _dream(world)

    assert report["imports_started"] == []
    assert report["budget"] == {"limit": 0.5, "spent": 0.6, "remaining": 0.0}
    assert {"kind": "import", "name": "Trip Planner",
            "reason": "today's import budget is used"} in report["skipped"]  # fmt: skip


async def test_budget_counts_only_todays_dream_imports(world):
    library, engine = world.library, world.engine
    world.metrics.spend = None  # no ledger: fall back to __total_cost__
    definition = library.get_workflow("Commons Import")
    await engine.create_process(definition, properties={DREAM_IMPORT_KEY: True,
                                                        "__total_cost__": 0.2})  # fmt: skip
    await engine.create_process(definition, properties={"__total_cost__": 5.0})  # owner's
    old = await engine.create_process(
        definition, properties={DREAM_IMPORT_KEY: True, "__total_cost__": 3.0}
    )
    old.created_at = datetime.now(UTC) - timedelta(days=1, hours=1)
    await engine.store.save_process(old)

    action = dream.CommonsDreamAction()
    context = type("Ctx", (), {"engine": engine})()
    assert await action.spent_today(context, library, world.metrics) == pytest.approx(0.2)


async def test_an_import_that_cannot_start_returns_the_offer_to_seen(world, monkeypatch):
    sha = await _publish_other(world, "Trip Planner", "Weekend trip itinerary", "Trip itinerary")
    await world.web.vouch(world.other.zebra_pubkey)
    _gap_workflow(world)

    async def refuse(*args, **kwargs):
        raise RuntimeError("launch refused")

    monkeypatch.setattr("zebra_tasks.launch.create_library_process", refuse)

    report = await _dream(world)

    assert report["imports_started"] == []
    assert any("launch refused" in e for e in report["errors"])
    assert (await world.exchange.offers.get(sha)).status == SEEN


async def test_judging_offer_is_not_started_again(world):
    sha = await _publish_other(world, "Trip Planner", "Weekend trip itinerary", "Trip itinerary")
    await world.web.vouch(world.other.zebra_pubkey)
    _gap_workflow(world)
    await world.exchange.offers.set_status(sha, JUDGING)

    report = await _dream(world)

    assert report["imports_started"] == []


# -- sharing promotion -------------------------------------------------------------------------


def _approve(library, n: int, reason: str | None = None, status: str = APPROVED) -> None:
    for i in range(n):
        record_share(library, f"W{i}", f"{i:064x}", "home", status, reason=reason)


async def test_enough_unchanged_approvals_ask_for_sharing_promotion(world):
    _approve(world.library, 5)

    report = await _dream(world)

    promotion = report["promotion"]
    assert (promotion["from_level"], promotion["to_level"]) == ("SUPERVISED", "SEMI_AUTONOMOUS")
    [suggestion] = await world.trust.list_suggestions(OWNER)
    assert suggestion.domain == "sharing" and suggestion.status == "pending"
    assert "approved my last 5 sharing proposals" in suggestion.evidence
    assert await world.trust.get_trust_level(OWNER, "sharing") == TrustLevel.SUPERVISED

    # Never twice while one is pending
    _approve(world.library, 5)
    again = await _dream(world)
    assert again["promotion"] is None
    assert len(await world.trust.list_suggestions(OWNER)) == 1


async def test_a_decline_or_a_note_restarts_the_count(world):
    _approve(world.library, 3)
    _approve(world.library, 1, status=DECLINED)
    _approve(world.library, 2)
    _approve(world.library, 1, reason="only after you fix the title")
    _approve(world.library, 4, reason="approved by the owner")

    assert sharing_approvals(world.library, None) == (4, 11)
    report = await _dream(world)
    assert report["promotion"] is None


async def test_autonomy_approvals_do_not_count(world):
    _approve(world.library, 5, reason="approved by earned sharing autonomy")

    assert sharing_approvals(world.library, None) == (0, 0)


async def test_only_approvals_after_the_last_sharing_change_count(world):
    _approve(world.library, 5)
    await world.trust.set_trust_level(
        OWNER, "sharing", TrustLevel.SEMI_AUTONOMOUS, "owner", "owner"
    )
    report = await _dream(world)
    assert report["promotion"] is None

    _approve(world.library, 5)
    report = await _dream(world)
    assert report["promotion"]["to_level"] == "AUTONOMOUS"


async def test_autonomous_sharing_asks_for_nothing(world):
    await world.trust.set_trust_level(OWNER, "sharing", TrustLevel.AUTONOMOUS, "owner", "owner")
    _approve(world.library, 10)

    report = await _dream(world)

    assert report["promotion"] is None
    assert await world.trust.list_suggestions(OWNER) == []


def test_settings_come_from_env_with_defaults(monkeypatch):
    from zebra.core.models import TaskInstance

    task = TaskInstance(id="t", process_id="p", task_definition_id="d", foe_id="f", properties={})
    assert dream.setting(task, "max_offers") == 1
    assert dream.setting(task, "daily_import_budget") == 0.5
    monkeypatch.setenv("ZEBRA_COMMONS_MAX_IMPORTS_PER_CYCLE", "3")
    monkeypatch.setenv("ZEBRA_COMMONS_OFFER_MIN_RATING", "nonsense")
    assert dream.setting(task, "max_imports") == 3
    assert dream.setting(task, "offer_min_rating") == 4.0
    task = TaskInstance(
        id="t", process_id="p", task_definition_id="d", foe_id="f", properties={"max_imports": 2}
    )
    assert dream.setting(task, "max_imports") == 2
