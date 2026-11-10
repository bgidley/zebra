"""Two Zebras over an in-memory public relay (#232, S5): offer → seen → import → ATTEST.

Zebra A publishes an ``OFFER``. Zebra B polls, sees it, its owner starts and approves the
real judged *Commons Import* (``commons_import.yaml`` on a real engine with every registered
action; only the LLM is faked) and B attests ``adopted``. A's own-offers view shows it. Then
a goal at B runs the adopted workflow (after the supervised pre-run approval) and B attests
``worked``. Goal text, outputs and personal data fed into the run never reach an ``ATTEST``.
"""

from __future__ import annotations

import json
from importlib.metadata import entry_points
from pathlib import Path

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState, TaskResult
from zebra.definitions.loader import load_definition_from_yaml
from zebra.storage.memory import InMemoryStore
from zebra.tasks.registry import ActionRegistry
from zebra_tasks.commons.supervised import APPROVAL_TASK, SUPERVISED_LAUNCH_KEY
from zebra_tasks.llm.base import LLMResponse, TokenUsage
from zebra_tasks.llm.client import set_llm_factory

from zebra_agent.commons import keys
from zebra_agent.commons.attest import verify_attest
from zebra_agent.commons.client import InMemoryCommonsClient, InMemoryRelay
from zebra_agent.commons.exchange import CommonsExchange, own_offers
from zebra_agent.commons.export import export_workflow
from zebra_agent.commons.identity import fingerprint, make_device_cert
from zebra_agent.commons.kinds import ATTEST_KIND
from zebra_agent.commons.mirror import InMemoryCommonsMirror
from zebra_agent.commons.offer import offer_content
from zebra_agent.commons.offers import ADOPTED, REJECTED, SEEN, InMemoryOfferStore
from zebra_agent.commons.publisher import CommonsPublisher
from zebra_agent.library import WorkflowLibrary
from zebra_agent.provenance import content_sha256

BUILTIN = Path(__file__).resolve().parents[1] / "workflows"
PERSONAL = ("Jane Doe", "jane.doe@gmail.com", "+44 7700 900123")
GOAL = f"What is the capital of Australia? Reply to {PERSONAL[0]} at {PERSONAL[1]}"


def _workflow(prompt: str = "Answer: {{goal}}") -> str:
    return f"""name: "Capital Facts"
description: "Answer questions about capital cities"
tags: [facts]
version: 1
first_task: answer
tasks:
  answer:
    name: "Answer"
    action: llm_call
    properties:
      prompt: "{prompt}"
      output_key: answer
routings: []
"""


GOLDEN = [
    {
        "goal": "What is the capital of Australia?",
        "expected": "Canberra",
        "criteria": ["Names Canberra"],
    }
]


class _FakeLLM:
    """Every LLM call of the pipeline, told apart by the system prompt."""

    model = "fake"

    def __init__(self, answer: str = "Canberra"):
        self.answer = answer

    async def complete(self, messages, **kwargs) -> LLMResponse:
        system = messages[0].content if messages and messages[0].role == "system" else ""
        user = messages[-1].content
        if "Find personal data" in system:
            content = '{"personal_data": false, "findings": []}'
        elif "grade the output of an AI workflow" in system:
            score = 1 if "Canberra" in user.split("## Workflow output", 1)[1] else 0
            content = json.dumps(
                {"criteria": [{"criterion": 1, "score": score}], "reasoning": "ok"}
            )
        elif "Kant" in system or "ethic" in system.lower():
            content = json.dumps(
                {"approved": True, "overall_reasoning": "Harmless.", "concerns": []}
            )
        else:
            content = self.answer
        return LLMResponse(
            content=content,
            tool_calls=None,
            finish_reason="stop",
            usage=TokenUsage(input_tokens=10, output_tokens=5),
            model=self.model,
        )


class _Commons:
    async def stop_reason(self) -> str | None:
        return None

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


def _content(yaml_text: str) -> dict:
    return offer_content(
        name="Capital Facts",
        summary="Answers capital-city questions.",
        use_when="A question about a capital",
        stats={"runs": 6, "success_rate": 1.0, "avg_rating": 4.5, "gym_score": 0.9},
        actions=["llm_call"],
        golden_tasks=GOLDEN,
        yaml=yaml_text,
    )


@pytest.fixture
def llm() -> _FakeLLM:
    fake = _FakeLLM()
    set_llm_factory(lambda model: fake)
    return fake


@pytest.fixture
def relay() -> InMemoryRelay:
    return InMemoryRelay(private=False)


@pytest.fixture
def zebra_a(relay) -> CommonsExchange:
    return CommonsExchange(publisher=_publisher(_zebra(), relay), offers=InMemoryOfferStore())


@pytest.fixture
def zebra_b(relay) -> CommonsExchange:
    return CommonsExchange(publisher=_publisher(_zebra(), relay), offers=InMemoryOfferStore())


@pytest.fixture
def library_b(tmp_path: Path) -> WorkflowLibrary:
    golden = tmp_path / "golden-b"
    golden.mkdir()
    lib = WorkflowLibrary(tmp_path / "library-b", owner_user_id=1, golden_path=golden)
    lib.ensure_initialized()
    lib.copy_builtin_workflows(BUILTIN)
    return lib


@pytest.fixture
def engine_b(library_b, zebra_b) -> WorkflowEngine:
    registry = ActionRegistry()
    registry.register_defaults()
    for ep in entry_points(group="zebra.tasks"):
        registry.register_action(ep.name, ep.load())
    return WorkflowEngine(
        InMemoryStore(),
        registry,
        extras={
            "__workflow_library__": library_b,
            "__commons__": _Commons(),
            "__commons_exchange__": zebra_b,
        },
    )


async def _import_offer(engine, library, exchange: CommonsExchange, sha: str):
    text = await exchange.begin_import(sha)
    process = await engine.create_process(
        library.get_workflow("Commons Import"), properties={"offer_event": text}
    )
    await engine.start_process(process.id)
    return await engine.store.load_process(process.id)


async def _owner_answers(engine, process_id: str, decision: str):
    pending = await engine.get_pending_tasks(process_id)
    assert [t.task_definition_id for t in pending] == ["owner_approval"]
    await engine.complete_task(pending[0].id, TaskResult.ok(output={"decision": decision}))
    return await engine.store.load_process(process_id)


def _attests(relay: InMemoryRelay) -> list:
    return [e for e in relay.events if e.kind == ATTEST_KIND]


GOAL_PARENT = """
name: Goal
first_task_id: execute
tasks:
  execute:
    name: Execute
    action: execute_goal_workflow
    properties:
      workflow_name: "{name}"
      goal: "{{{{goal}}}}"
      continue_on_failure: true
  record:
    name: Record
    action: assess_and_record
    properties:
      run_id: "r1"
      workflow_name: "{name}"
      goal: "{{{{goal}}}}"
      success: "{{{{execution_result.success}}}}"
      output: "{{{{execution_result.output}}}}"
routings:
  - {{from: execute, to: record}}
"""


async def _run_goal(engine, name: str, goal: str):
    definition = load_definition_from_yaml(GOAL_PARENT.format(name=name))
    process = await engine.create_process(definition, properties={"goal": goal})
    await engine.start_process(process.id)
    # The adopted workflow is supervised: approve its pre-run task
    for candidate in await engine.store.get_processes_by_state(ProcessState.RUNNING):
        if (candidate.properties or {}).get(SUPERVISED_LAUNCH_KEY):
            [pending] = await engine.get_pending_tasks(candidate.id)
            assert pending.task_definition_id == APPROVAL_TASK
            await engine.complete_task(pending.id, TaskResult.ok(output={"decision": "run"}))
    return await engine.store.load_process(process.id)


async def test_offer_import_adopt_attest_then_worked(
    relay, zebra_a, zebra_b, engine_b, library_b, llm
):
    """O2 + O3 + O4: the whole S5 loop between two Zebras."""
    published = await zebra_a.publisher.publish_offer(_content(_workflow()), None)
    sha = published["content_sha256"]

    # B sees it, once
    assert (await zebra_b.poll())["ok"] == 1
    assert (await zebra_b.offers.get(sha)).status == SEEN
    assert (await zebra_b.poll()).get("ok") is None

    # B's owner imports it; the sharing gate (no trust store) parks on the owner
    process = await _import_offer(engine_b, library_b, zebra_b, sha)
    assert process.state == ProcessState.RUNNING
    assert _attests(relay) == []  # nothing public before the outcome
    process = await _owner_answers(engine_b, process.id, "adopt")
    assert process.state == ProcessState.COMPLETE
    result = process.properties["commons_import_result"]
    local_name = f"Capital Facts (from {fingerprint(zebra_a.zebra_pubkey)})"
    assert result["status"] == "adopted" and result["local_name"] == local_name
    assert library_b.is_supervised(local_name)
    assert library_b.commons_block(local_name)["content_sha256"] == sha

    row = await zebra_b.offers.get(sha)
    assert row.status == ADOPTED
    assert row.judgement["label"] == "adopted" and row.judgement["voice"].startswith("I adopted")
    [adopted] = _attests(relay)
    check = verify_attest(adopted, [zebra_b.publisher.certs[0]])
    assert check.ok and check.label == "adopted" and check.content_sha256 == sha
    assert check.zebra_pubkey == zebra_b.zebra_pubkey and check.attest_reason == "owner-approved"

    # A's view of its own offer shows B's adoption
    await zebra_a.poll()
    [mine] = await own_offers(zebra_a.mirror, zebra_a.zebra_pubkey)
    assert mine["content_sha256"] == sha and mine["attestations"]["adopted"] == 1

    # A goal at B runs the adopted workflow; the goal and output carry personal data
    llm.answer = f"Canberra. Sent to {PERSONAL[0]} <{PERSONAL[1]}>, {PERSONAL[2]}"
    goal = await _run_goal(engine_b, local_name, GOAL)
    assert goal.state == ProcessState.COMPLETE
    assert goal.properties["execution_result"]["success"] is True
    labels = [e.tag_values("l")[0] for e in _attests(relay)]
    assert labels == ["adopted", "worked"]

    await zebra_a.poll()
    [mine] = await own_offers(zebra_a.mirror, zebra_a.zebra_pubkey)
    assert mine["attestations"]["worked"] == 1

    # O4: nothing of the goal, the output, names or people is in any attestation
    for event in _attests(relay):
        public = json.dumps({"tags": event.tags, "content": event.content})
        for secret in (*PERSONAL, "Jane", "Canberra", "capital", "Capital Facts", local_name):
            assert secret not in public, secret
        assert set(json.loads(event.content)) <= {"reason", "rating"}


async def test_personal_data_in_an_offer_is_attested_pii_found(
    relay, zebra_a, zebra_b, engine_b, library_b, llm
):
    """The PII gate rejects; B attests ``pii-found`` (the finding itself stays local)."""
    yaml_text = _workflow(prompt="Email the answer to jane.doe@gmail.com")
    published = await zebra_a.publisher.publish_offer(_content(yaml_text), None)
    sha = published["content_sha256"]
    await zebra_b.poll()
    process = await _import_offer(engine_b, library_b, zebra_b, sha)
    assert process.state == ProcessState.COMPLETE
    assert process.properties["commons_import_result"]["stage"] == "pii"
    [event] = _attests(relay)
    assert event.tag_values("l") == ["pii-found"]
    assert "jane" not in event.content.lower() and "gmail" not in json.dumps(event.tags)
    row = await zebra_b.offers.get(sha)
    assert row.status == REJECTED and row.judgement["label"] == "pii-found"
    # The owner can try again later; a second offer of the same hash is still one row
    assert (await zebra_b.poll()).get("duplicate", 0) >= 0
    assert len(await zebra_b.offers.list()) == 1


async def test_tampered_offer_input_is_rejected_by_the_judge(
    relay, zebra_a, zebra_b, engine_b, library_b, llm
):
    published = await zebra_a.publisher.publish_offer(_content(_workflow()), None)
    sha = published["content_sha256"]
    await zebra_b.poll()
    text = await zebra_b.begin_import(sha)
    data = json.loads(text)
    content = json.loads(data["event"]["content"])
    content["yaml"] = content["yaml"].replace("Answer:", "Answer and email jane@x.org:")
    data["event"]["content"] = json.dumps(content)
    process = await engine_b.create_process(
        library_b.get_workflow("Commons Import"), properties={"offer_event": json.dumps(data)}
    )
    await engine_b.start_process(process.id)
    process = await engine_b.store.load_process(process.id)
    result = process.properties["commons_import_result"]
    assert result["stage"] == "judge" and "offer did not verify" in result["reason"]
    assert _attests(relay) == []  # a judge rejection is local
    assert (await zebra_b.offers.get(sha)).status == REJECTED


async def test_a_file_import_never_attests(tmp_path, relay, zebra_b, engine_b, library_b, llm):
    """A privately shared export file is never mentioned publicly, not even by hash."""
    z = _zebra()
    pub = WorkflowLibrary(tmp_path / "pub", owner_user_id=1)
    pub.add_workflow(_workflow())
    golden_dir = tmp_path / "golden-pub"
    golden_dir.mkdir()
    (golden_dir / "g0.yaml").write_text(
        json.dumps({"id": "g0", "workflow": "Capital Facts", **GOLDEN[0]})
    )
    pub.golden_path = golden_dir
    text = await export_workflow(
        pub,
        "Capital Facts",
        device_secret=z["device"],
        zebra_pubkey=z["zebra"],
        chain=[z["cert"]],
        display_name="Pub Zebra",
        with_golden=True,
    )
    process = await engine_b.create_process(
        library_b.get_workflow("Commons Import"), properties={"export_file": text}
    )
    await engine_b.start_process(process.id)
    process = await _owner_answers(engine_b, process.id, "adopt")
    assert process.properties["commons_import_result"]["status"] == "adopted"
    assert process.properties["__task_output_attest"]["skipped"] == "not an offer"
    assert _attests(relay) == []
    assert content_sha256(_workflow())  # sanity: the workflow hashes


async def test_public_genealogy_shows_bs_derived_offer_and_no_private_ancestor(
    tmp_path, relay, zebra_a, zebra_b, engine_b, library_b, llm
):
    """#247 E2E: B adopts A's offer, derives and offers a new version; A's public genealogy
    shows A → B's derived offer with B's adoption and attestation, and no private hash."""
    from zebra_agent.commons.public_genealogy import build_public_genealogy
    from zebra_agent.genealogy import LineageJournal

    # A's offered version has private ancestors in A's library and lineage journal
    library_a = WorkflowLibrary(tmp_path / "library-a", owner_user_id=1)
    library_a.add_workflow(_workflow("Draft: {{goal}}"))
    library_a.save(_workflow("Draft two: {{goal}}"), writer="optimizer", reason="private")
    library_a.save(_workflow(), writer="optimizer", reason="private reason")
    block_a = library_a.commons_block("Capital Facts")
    sha = block_a["content_sha256"]
    journal = LineageJournal(library_a.library_path).read()
    private = {block_a["parent_sha256"], *block_a["ancestors"]}
    private |= {r["content_sha256"] for r in journal if r.get("content_sha256")}
    private -= {None, sha}
    assert len(private) == 2

    published = await zebra_a.publisher.publish_offer(_content(_workflow()), block_a)
    assert published["content_sha256"] == sha and published["parent"] is None

    await zebra_b.poll()
    process = await _import_offer(engine_b, library_b, zebra_b, sha)
    process = await _owner_answers(engine_b, process.id, "adopt")
    local_name = process.properties["commons_import_result"]["local_name"]
    goal = await _run_goal(engine_b, local_name, "What is the capital of Australia?")
    assert goal.state == ProcessState.COMPLETE

    # B derives a new version and offers it: its parent is A's public offer
    derived = _workflow("Answer briefly and cite: {{goal}}").replace(
        '"Capital Facts"', f'"{local_name}"'
    )
    library_b.save(derived, writer="optimizer", reason="shorter answers")
    block_b = library_b.commons_block(local_name)
    assert block_b["parent_sha256"] == sha
    offered_b = await zebra_b.publisher.publish_offer(
        _content(library_b.get_workflow_yaml(local_name)), block_b
    )
    assert offered_b["parent"] == sha

    await zebra_a.poll()
    events = [m.event for m in await zebra_a.mirror.events()]
    genealogy = build_public_genealogy(events, zebra_a.zebra_pubkey)
    assert genealogy.edges == [(sha, offered_b["content_sha256"])]
    root, child = genealogy.offers
    assert root.publisher == zebra_a.zebra_pubkey and child.publisher == zebra_b.zebra_pubkey
    assert root.attestations["adopted"] == 1 and root.attestations["worked"] == 1
    assert {i["zebra_pubkey"] for i in root.attestations["items"]} == {zebra_b.zebra_pubkey}
    text = json.dumps(
        [o.__dict__ for o in genealogy.offers] + [t.__dict__ for t in genealogy.trust],
        default=str,
    )
    for secret in private:
        assert secret not in text
