"""The owner-governed ``sharing`` trust domain (REQ-NET-006, #229 S2b).

A trust gate on ``sharing`` reads the Commons owner's level (from the workflow
library), whoever the process runs for, and fails closed with no owner.
"""

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState, TaskResult
from zebra.definitions import load_definition_from_yaml
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import ExecutionContext, RouteNameCondition, TaskAction
from zebra.tasks.registry import ActionRegistry
from zebra_agent.storage.trust import (
    DEFAULT_DOMAINS,
    OWNER_GOVERNED_DOMAINS,
    InMemoryTrustStore,
    TrustLevel,
)

from zebra_tasks.agent import trust_gate
from zebra_tasks.agent.trust_gate import DECISIONS_KEY, TrustGateAction

SHARE_YAML = """
name: "Share Workflow"
first_task_id: check_trust
tasks:
  check_trust:
    name: "Check Trust"
    action: trust_gate
    properties:
      domain: "sharing"
      action_description: "offer a workflow to the Commons"
  request_approval:
    name: "Approve Share"
    auto: false
  publish:
    name: "Publish"
    action: recording
routings:
  - {from: check_trust, to: publish, condition: route_name, name: proceed}
  - {from: check_trust, to: request_approval, condition: route_name, name: approve}
  - {from: request_approval, to: publish}
"""

OWNER, OTHER = 1, 2


class RecordingAction(TaskAction):
    executed = 0

    async def run(self, task, context: ExecutionContext) -> TaskResult:
        RecordingAction.executed += 1
        return TaskResult.ok(output={"done": True})


class FakeLibrary:
    def __init__(self, owner, error: Exception | None = None):
        self.owner = owner
        self.error = error

    async def refresh_owner(self):
        if self.error:
            raise self.error
        return self.owner


@pytest.fixture(autouse=True)
def _reset():
    RecordingAction.executed = 0


async def _run(trust_store, library, user_id=OTHER):
    registry = ActionRegistry()
    registry.register_action("trust_gate", TrustGateAction)
    registry.register_action("recording", RecordingAction)
    registry.register_condition("route_name", RouteNameCondition)
    extras = {"__trust_store__": trust_store}
    if library is not None:
        extras["__workflow_library__"] = library
    engine = WorkflowEngine(InMemoryStore(), registry, extras=extras)
    process = await engine.create_process(
        load_definition_from_yaml(SHARE_YAML), properties={"__user_id__": user_id}
    )
    await engine.start_process(process.id)
    process = await engine.store.load_process(process.id)
    return process, process.properties[DECISIONS_KEY][-1]


def test_sharing_is_a_default_owner_governed_domain():
    assert "sharing" in DEFAULT_DOMAINS
    assert OWNER_GOVERNED_DOMAINS == trust_gate.OWNER_GOVERNED_DOMAINS == {"sharing"}


async def test_owner_level_governs_a_non_owner_process():
    store = InMemoryTrustStore()
    await store.set_trust_level(
        OWNER, "sharing", TrustLevel.AUTONOMOUS, reason="test", changed_by="human"
    )
    process, decision = await _run(store, FakeLibrary(OWNER), user_id=OTHER)
    assert decision["route"] == "proceed"
    assert decision["user_id"] == OWNER
    assert process.state == ProcessState.COMPLETE
    assert RecordingAction.executed == 1


async def test_non_owner_autonomy_does_not_count():
    store = InMemoryTrustStore()
    await store.set_trust_level(
        OTHER, "sharing", TrustLevel.AUTONOMOUS, reason="test", changed_by="human"
    )
    process, decision = await _run(store, FakeLibrary(OWNER), user_id=OTHER)
    assert decision["route"] == "approve"
    assert decision["level"] == "SUPERVISED"
    # Approval blocks the share: the process waits and nothing is published.
    assert process.state == ProcessState.RUNNING
    assert RecordingAction.executed == 0


@pytest.mark.parametrize(
    "library",
    [None, FakeLibrary(None), FakeLibrary(OWNER, error=RuntimeError("db down"))],
    ids=["no-library", "no-owner", "lookup-error"],
)
async def test_unknown_owner_fails_closed(library):
    store = InMemoryTrustStore()
    for uid in (OWNER, OTHER):
        await store.set_trust_level(
            uid, "sharing", TrustLevel.AUTONOMOUS, reason="test", changed_by="human"
        )
    process, decision = await _run(store, library, user_id=OWNER)
    assert decision["route"] == "approve"
    assert "failing closed" in decision["reason"]
    assert RecordingAction.executed == 0


async def test_other_domains_still_follow_the_process_user():
    store = InMemoryTrustStore()
    await store.set_trust_level(
        OTHER, "code", TrustLevel.AUTONOMOUS, reason="test", changed_by="human"
    )
    registry = ActionRegistry()
    registry.register_action("trust_gate", TrustGateAction)
    registry.register_action("recording", RecordingAction)
    registry.register_condition("route_name", RouteNameCondition)
    engine = WorkflowEngine(
        InMemoryStore(),
        registry,
        extras={"__trust_store__": store, "__workflow_library__": FakeLibrary(OWNER)},
    )
    definition = load_definition_from_yaml(SHARE_YAML.replace('"sharing"', '"code"'))
    process = await engine.create_process(definition, properties={"__user_id__": OTHER})
    await engine.start_process(process.id)
    process = await engine.store.load_process(process.id)
    assert process.properties[DECISIONS_KEY][-1]["user_id"] == OTHER
    assert process.properties[DECISIONS_KEY][-1]["route"] == "proceed"
