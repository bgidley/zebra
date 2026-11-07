"""The *Commons Offer* workflow end to end over an in-memory public relay (#231, S4).

Runs the real ``commons_offer.yaml`` on a real engine with every registered action. The relay
is an ``InMemoryRelay`` behind the real public write policy
(``deploy/podman/commons-relay/write_policy.py``), and the real ``ReceiptSigner`` signs a
receipt for every line the policy journals. Only the LLM is faked: the listing writer answers
an honest summary, the personal-data scan finds nothing and the ethics gate approves.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import shutil
from importlib.metadata import entry_points
from pathlib import Path

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState, TaskResult
from zebra.storage.memory import InMemoryStore
from zebra.tasks.registry import ActionRegistry
from zebra_tasks.llm.base import LLMResponse, TokenUsage
from zebra_tasks.llm.client import set_llm_factory

from zebra_agent.commons import keys
from zebra_agent.commons.client import Filter, InMemoryCommonsClient, InMemoryRelay, PublishRefused
from zebra_agent.commons.identity import make_device_cert
from zebra_agent.commons.kinds import DEVICE_CERT_KIND, OFFER_KIND, RECEIPT_KIND
from zebra_agent.commons.mirror import InMemoryCommonsMirror
from zebra_agent.commons.offer import publish_refusal, verify_offer
from zebra_agent.commons.publisher import PUBLISHER_KEY, CommonsPublisher
from zebra_agent.commons.receipts import ReceiptSigner, receipt_order
from zebra_agent.commons.sync import share_records
from zebra_agent.library import WorkflowLibrary
from zebra_agent.metrics import WorkflowStats
from zebra_agent.storage.trust import InMemoryTrustStore, TrustLevel

REPO = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO / "zebra-agent" / "workflows"
OWNER = 1
NAME = "Capital Facts"
YAML = f"""name: "{NAME}"
description: "Answer questions about capital cities"
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


def _load_policy():
    path = REPO / "deploy" / "podman" / "commons-relay" / "write_policy.py"
    spec = importlib.util.spec_from_file_location("commons_wp_e2e", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


wp = _load_policy()


class PolicyClient(InMemoryCommonsClient):
    """A public relay client whose relay runs the real write policy, as strfry would."""

    def __init__(self, relay: InMemoryRelay, policy):
        super().__init__(relay)
        self.policy = policy

    async def publish(self, event):
        self.check_publish(event)
        action, message = self.policy.decide({"type": "new", "event": event.to_dict()})
        if action != "accept":
            raise PublishRefused(f"the relay refused the event: {message}")
        self.relay.store(event)


class FakeLLM:
    model = "fake"

    def __init__(self):
        self.calls: list[str] = []
        self.listing = {
            "summary": "Answers questions about capital cities; 5 of 5 runs succeeded here.",
            "use_when": "Someone asks for the capital of a country",
            "golden_tasks": [
                {
                    "goal": "What is the capital of Australia?",
                    "expected": "Canberra",
                    "criteria": ["Names Canberra"],
                }
            ],
        }

    async def complete(self, messages, **kwargs) -> LLMResponse:
        system = messages[0].content if messages and messages[0].role == "system" else ""
        if "public listing" in system:
            kind, content = "listing", json.dumps(self.listing)
        elif "Find personal data" in system:
            kind, content = "pii", '{"personal_data": false, "findings": []}'
        elif "Kant" in system or "ethic" in system.lower():
            kind = "ethics"
            content = json.dumps(
                {
                    "approved": True,
                    "overall_reasoning": "A harmless facts workflow.",
                    "concerns": [],
                }
            )
        else:
            kind, content = "other", "{}"
        self.calls.append(kind)
        return LLMResponse(
            content=content,
            tool_calls=None,
            finish_reason="stop",
            usage=TokenUsage(input_tokens=10, output_tokens=5),
            model=self.model,
        )


class Stats:
    def __init__(self, runs: int):
        self.runs = runs

    async def get_stats(self, name):
        return WorkflowStats(name, total_runs=self.runs, successful_runs=self.runs, avg_rating=4.0)


@pytest.fixture
def llm():
    fake = FakeLLM()
    set_llm_factory(lambda model: fake)
    return fake


@pytest.fixture
def world(tmp_path, llm):
    """One Zebra's home device, a public relay with the real policy and receipt signer."""
    zebra_secret = keys.generate_secret_key()
    operator = keys.generate_secret_key()
    secrets = {"home": keys.generate_secret_key(), "work": keys.generate_secret_key()}
    certs = [
        make_device_cert(
            zebra_secret, keys.public_key(secrets[s]), label=f"{s} box", sphere=s, observed=o
        )
        for s, o in (("home", False), ("work", True))
    ]
    policy_file = tmp_path / "relay" / "policy.json"
    policy_file.parent.mkdir()
    policy_file.write_text(json.dumps({"operator_pubkey": keys.public_key(operator)}))
    journal = tmp_path / "relay" / "journal.jsonl"
    policy = wp.Policy(str(policy_file), str(journal))
    relay = InMemoryRelay(private=False)
    signer = ReceiptSigner(
        journal, tmp_path / "relay" / "signer.json", PolicyClient(relay, policy), operator
    )
    builtins = tmp_path / "builtins"
    builtins.mkdir()
    shutil.copy(WORKFLOWS / "commons_offer.yaml", builtins / "commons_offer.yaml")

    def device(sphere: str = "home", runs: int = 5):
        stats = Stats(runs)
        library = WorkflowLibrary(
            tmp_path / sphere, stats, owner_user_id=OWNER, sphere=sphere, device=sphere
        )
        library.copy_builtin_workflows(builtins)
        publisher = CommonsPublisher(
            canonical=PolicyClient(relay, policy),
            device_secret=secrets[sphere],
            zebra_pubkey=keys.public_key(zebra_secret),
            mirror=InMemoryCommonsMirror(),
            certs=list(certs),
            sphere=sphere,
            observed=sphere == "work",
            receipt_pubkey=keys.public_key(operator),
            receipt_wait=5,
            receipt_poll=0.02,
        )
        registry = ActionRegistry()
        registry.register_defaults()
        for ep in entry_points(group="zebra.tasks"):
            registry.register_action(ep.name, ep.load())
        trust = InMemoryTrustStore()
        engine = WorkflowEngine(
            InMemoryStore(),
            registry,
            extras={
                "__workflow_library__": library,
                PUBLISHER_KEY: publisher,
                "__trust_store__": trust,
            },
        )
        return type(
            "Device",
            (),
            {"library": library, "engine": engine, "publisher": publisher, "trust": trust,
             "stats": stats},
        )  # fmt: skip

    world = type("World", (), {})()
    world.relay, world.signer, world.device = relay, signer, device
    world.zebra_npub = keys.npub_encode(keys.public_key(zebra_secret))
    world.operator_pubkey = keys.public_key(operator)
    world.certs = certs
    return world


@pytest.fixture
async def signing(world):
    """The receipt sidecar, running while the test does."""
    task = asyncio.create_task(world.signer.run(interval=0.02))
    yield
    task.cancel()


async def _offer(dev, name: str = NAME):
    definition = dev.library.get_workflow("Commons Offer")
    process = await dev.engine.create_process(
        definition, properties={"workflow_name": name, "__user_id__": OWNER}
    )
    await dev.engine.start_process(process.id)
    return await dev.engine.store.load_process(process.id)


async def _answer(dev, process_id: str, decision: str):
    pending = await dev.engine.get_pending_tasks(process_id)
    assert [t.task_definition_id for t in pending] == ["owner_approval"]
    await dev.engine.complete_task(pending[0].id, TaskResult.ok(output={"decision": decision}))
    return await dev.engine.store.load_process(process_id)


def _offers(relay: InMemoryRelay):
    return [e for e in relay.events if e.kind == OFFER_KIND]


def _result(process) -> dict:
    return process.properties["commons_offer_result"]


async def test_owner_approves_and_one_offer_with_a_receipt_reaches_the_relay(world, signing):
    """O2: >= 5 runs, owner approves, one OFFER with a receipt that verifies against the npub."""
    dev = world.device()
    dev.library.save(YAML, writer="human")
    process = await _offer(dev)
    assert process.state == ProcessState.RUNNING  # SUPERVISED sharing: the owner decides
    assert "Capital Facts" in process.properties["offer"]["review"]
    assert _offers(world.relay) == []

    process = await _answer(dev, process.id, "publish")

    assert process.state == ProcessState.COMPLETE
    result = _result(process)
    assert result["status"] == "published"
    [offer] = _offers(world.relay)
    assert result["event_id"] == offer.id
    zebra_hex = keys.npub_decode(world.zebra_npub)
    certs = [e for e in world.relay.events if e.kind == DEVICE_CERT_KIND]
    check = verify_offer(offer, certs, expected_zebra=zebra_hex)
    assert check.ok, check.reason
    assert check.content_sha256 == dev.library.commons_block(NAME)["content_sha256"]
    assert check.parent is None  # first public version: no ancestor named
    receipts = [e for e in world.relay.events if e.kind == RECEIPT_KIND]
    order = receipt_order(receipts, world.operator_pubkey)
    assert offer.id in order and result["receipt_seq"] == order[offer.id]
    # The receipt orders the offer after the device cert that attributes it.
    assert order[certs[0].id] < order[offer.id]
    # The local mirror holds the cert, the offer and its receipt.
    mirrored = {m.event.kind for m in await dev.publisher.mirror.events()}
    assert mirrored == {DEVICE_CERT_KIND, OFFER_KIND, RECEIPT_KIND}
    # 'public' was approved through share_with and recorded like any share.
    assert "public" in dev.library.commons_block(NAME)["share_with"]
    statuses = [r["status"] for r in share_records(dev.library) if r["sphere"] == "public"]
    assert statuses == ["approved", "sent"]
    # A second offer of the same version is refused.
    again = await _offer(dev)
    assert _result(again)["reason"] == "this version is already offered"
    assert len(_offers(world.relay)) == 1


async def test_owner_keeps_it_private(world):
    dev = world.device()
    dev.library.save(YAML, writer="human")
    process = await _offer(dev)
    process = await _answer(dev, process.id, "keep")
    assert _result(process)["status"] == "declined"
    assert world.relay.events == []
    assert "public" not in dev.library.commons_block(NAME)["share_with"]


async def test_earned_sharing_autonomy_publishes_without_asking(world, signing):
    dev = world.device()
    await dev.trust.set_trust_level(OWNER, "sharing", TrustLevel.AUTONOMOUS, "test", "test")
    dev.library.save(YAML, writer="human")
    process = await _offer(dev)
    assert process.state == ProcessState.COMPLETE
    assert _result(process)["status"] == "published"
    assert len(_offers(world.relay)) == 1


async def test_observed_taint_needs_the_owner_whatever_the_trust_level(world):
    dev = world.device("work")  # saved on the observed work laptop: tainted_by [work]
    await dev.trust.set_trust_level(OWNER, "sharing", TrustLevel.AUTONOMOUS, "test", "test")
    dev.library.save(YAML, writer="human")
    process = await _offer(dev)
    assert process.state == ProcessState.RUNNING
    assert process.properties["offer"]["observed_taint"] == ["work"]
    assert [t.task_definition_id for t in await dev.engine.get_pending_tasks(process.id)] == [
        "owner_approval"
    ]
    assert world.relay.events == []


async def test_too_few_runs_is_refused_with_a_reason(world):
    dev = world.device(runs=4)
    dev.library.save(YAML, writer="human")
    process = await _offer(dev)
    assert process.state == ProcessState.COMPLETE
    result = _result(process)
    assert (result["status"], result["stage"]) == ("refused", "prepare")
    assert "4 recorded run(s)" in result["reason"] and "at least 5" in result["reason"]
    assert world.relay.events == []


async def test_system_workflow_is_not_exportable(world):
    dev = world.device()
    dev.library.save(YAML.replace("tags: [facts]", "tags: [facts, system]"), writer="human")
    result = _result(await _offer(dev))
    assert result["status"] == "refused" and "may not leave" in result["reason"]


async def test_foreign_users_workflow_is_refused(world):
    from zebra_agent.provenance import Exposure

    dev = world.device()
    dev.library.save(YAML, writer="human", exposure=Exposure(user_ids=[OWNER, 2]))
    result = _result(await _offer(dev))
    assert result["status"] == "refused" and "may not leave" in result["reason"]


async def test_leak_guard_kept_is_refused(world):
    dev = world.device()
    dev.library.save(YAML, writer="optimizer", leak={"status": "kept", "hits": []})
    result = _result(await _offer(dev))
    assert result["status"] == "refused" and "leak guard" in result["reason"]


async def test_no_publisher_fails_closed(world):
    dev = world.device()
    dev.engine.extras.pop(PUBLISHER_KEY)
    dev.library.save(YAML, writer="human")
    result = _result(await _offer(dev))
    assert result["status"] == "refused" and "ZEBRA_COMMONS_RELAYS" in result["reason"]


async def test_personal_data_in_the_listing_is_refused(world, llm):
    llm.listing["golden_tasks"][0]["goal"] = "What is Jane Smith's home town?"
    original = llm.complete

    async def scan(messages, **kwargs):
        system = messages[0].content if messages[0].role == "system" else ""
        if "Find personal data" in system and "Jane Smith" in messages[-1].content:
            findings = [{"text": "Jane Smith", "kind": "name", "where": "golden_tasks"}]
            content = json.dumps({"personal_data": True, "findings": findings})
            return LLMResponse(content=content, tool_calls=None, finish_reason="stop",
                               usage=TokenUsage(1, 1), model="fake")  # fmt: skip
        return await original(messages, **kwargs)

    llm.complete = scan
    dev = world.device()
    dev.library.save(YAML, writer="human")
    result = _result(await _offer(dev))
    assert (result["status"], result["stage"]) == ("refused", "pii")
    assert world.relay.events == []


async def test_approval_void_when_the_workflow_changed_meanwhile(world):
    dev = world.device()
    dev.library.save(YAML, writer="human")
    process = await _offer(dev)
    # Saved again while the owner was deciding: a new version, share_with reset.
    parent = dev.library.commons_block(NAME)["content_sha256"]
    dev.library.save(YAML.replace("Answer:", "Answer briefly:"), writer="human", parent=parent)
    process = await _answer(dev, process.id, "publish")
    result = _result(process)
    assert result["status"] == "declined" and "changed" in result["reason"]
    assert world.relay.events == []


async def test_publish_refuses_without_public_in_share_with(world):
    dev = world.device()
    dev.library.save(YAML, writer="human")
    info = await dev.library.get_workflow_info(NAME)
    digest = info.commons["content_sha256"]
    assert "share_with" in publish_refusal(info, dev.library, 5, digest)
    assert dev.library.approve_share(NAME, "public", digest)
    info = await dev.library.get_workflow_info(NAME)
    assert publish_refusal(info, dev.library, 5, digest) is None
    assert "changed" in publish_refusal(info, dev.library, 5, "ff" * 32)


async def test_commons_publish_refuses_outside_the_shipped_workflow(world):
    dev = world.device()
    dev.library.save(YAML, writer="human")
    rogue = """name: Rogue
first_task: publish
tasks:
  publish:
    name: Publish
    action: commons_publish
"""
    from zebra.definitions.loader import load_definition_from_yaml

    definition = load_definition_from_yaml(rogue)
    process = await dev.engine.create_process(definition, properties={"offer": {"name": NAME}})
    await dev.engine.start_process(process.id)
    process = await dev.engine.store.load_process(process.id)
    assert process.state == ProcessState.FAILED
    assert world.relay.events == []
    fetched = await dev.publisher.canonical.fetch([Filter(kinds=(OFFER_KIND,))])
    assert fetched == []
