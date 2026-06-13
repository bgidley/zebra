"""End-to-end trust gate test (F13 / REQ-TRUST-003).

Runs a real workflow through the engine: the trust_gate routes to a human
approval task (auto: false) when the domain is SUPERVISED — pausing the
workflow — and a human completing that task resumes it to COMPLETE. At
AUTONOMOUS the gate proceeds directly and the human task never runs.
"""

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState, TaskResult, TaskState
from zebra.definitions import load_definition_from_yaml
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import ExecutionContext, RouteNameCondition, TaskAction
from zebra.tasks.registry import ActionRegistry

from zebra_tasks.agent.trust_gate import DECISIONS_KEY, TrustGateAction

GATED_WORKFLOW_YAML = """
id: gated_deploy
name: "Gated Deploy"
first_task_id: check_trust
tasks:
  check_trust:
    name: "Check Trust"
    action: trust_gate
    properties:
      domain: "code"
      action_description: "deploy to production"
  request_approval:
    name: "Approve Deploy"
    auto: false
    properties:
      schema:
        type: object
        title: "Approve deploy to production?"
        properties:
          comment:
            type: string
            title: "Comment"
  execute_action:
    name: "Execute Action"
    action: recording
routings:
  - from: check_trust
    to: execute_action
    condition: route_name
    name: "proceed"
  - from: check_trust
    to: request_approval
    condition: route_name
    name: "approve"
  - from: request_approval
    to: execute_action
"""


class RecordingAction(TaskAction):
    """Counts executions so tests can assert the gated step ran (or not)."""

    executed = 0

    async def run(self, task, context: ExecutionContext) -> TaskResult:
        RecordingAction.executed += 1
        return TaskResult.ok(output={"done": True})


class FakeTrustStore:
    """Minimal duck-typed trust store with a fixed level per (user, domain)."""

    def __init__(self, level: str):
        self.level = level
        self.calls: list[tuple[int, str]] = []

    async def get_trust_level(self, user_id: int, domain: str) -> str:
        self.calls.append((user_id, domain))
        return self.level


@pytest.fixture(autouse=True)
def _reset_counter():
    RecordingAction.executed = 0


def _make_engine(trust_store) -> WorkflowEngine:
    registry = ActionRegistry()
    registry.register_action("trust_gate", TrustGateAction)
    registry.register_action("recording", RecordingAction)
    registry.register_condition("route_name", RouteNameCondition)
    store = InMemoryStore()
    return WorkflowEngine(store, registry, extras={"__trust_store__": trust_store})


async def test_supervised_pauses_then_human_approval_resumes():
    """SUPERVISED: gate routes to the human task, approval resumes to COMPLETE."""
    trust_store = FakeTrustStore("SUPERVISED")
    engine = _make_engine(trust_store)
    definition = load_definition_from_yaml(GATED_WORKFLOW_YAML)

    process = await engine.create_process(definition, properties={"__user_id__": 1})
    await engine.start_process(process.id)

    # Paused: process still RUNNING, human approval task READY, action not executed
    process = await engine.store.load_process(process.id)
    assert process.state == ProcessState.RUNNING
    assert RecordingAction.executed == 0

    pending = await engine.get_pending_tasks(process.id)
    assert len(pending) == 1
    approval_task = pending[0]
    assert approval_task.task_definition_id == "request_approval"
    assert approval_task.state == TaskState.READY

    # Gate consulted the store for the right (user, domain) and audited its decision
    assert trust_store.calls == [(1, "code")]
    decisions = process.properties[DECISIONS_KEY]
    assert len(decisions) == 1
    assert decisions[0]["route"] == "approve"
    assert decisions[0]["level"] == "SUPERVISED"

    # Human approves — workflow resumes and completes
    await engine.complete_task(approval_task.id, TaskResult.ok(output={"comment": "lgtm"}))

    process = await engine.store.load_process(process.id)
    assert process.state == ProcessState.COMPLETE
    assert RecordingAction.executed == 1


async def test_autonomous_skips_approval_entirely():
    """AUTONOMOUS: gate proceeds straight to the action; no pending human task."""
    engine = _make_engine(FakeTrustStore("AUTONOMOUS"))
    definition = load_definition_from_yaml(GATED_WORKFLOW_YAML)

    process = await engine.create_process(definition, properties={"__user_id__": 1})
    await engine.start_process(process.id)

    process = await engine.store.load_process(process.id)
    assert process.state == ProcessState.COMPLETE
    assert RecordingAction.executed == 1
    assert process.properties[DECISIONS_KEY][0]["route"] == "proceed"


async def test_semi_autonomous_without_declaration_pauses():
    """SEMI_AUTONOMOUS with no reversibility declaration still needs approval."""
    engine = _make_engine(FakeTrustStore("SEMI_AUTONOMOUS"))
    definition = load_definition_from_yaml(GATED_WORKFLOW_YAML)

    process = await engine.create_process(definition, properties={"__user_id__": 1})
    await engine.start_process(process.id)

    process = await engine.store.load_process(process.id)
    assert process.state == ProcessState.RUNNING
    pending = await engine.get_pending_tasks(process.id)
    assert [t.task_definition_id for t in pending] == ["request_approval"]


# =============================================================================
# F14: contextual reversibility assessment (issue #14 e2e criterion)
# =============================================================================

ASSESSED_WORKFLOW_YAML = """
id: assessed_cleanup
name: "Assessed Cleanup"
first_task_id: check_trust
tasks:
  check_trust:
    name: "Check Trust"
    action: trust_gate
    properties:
      domain: "code"
      action_description: "delete files"
      target_task_id: "delete_files"
  request_approval:
    name: "Approve Deletion"
    auto: false
    properties:
      schema:
        type: object
        title: "Approve file deletion?"
  delete_files:
    name: "Delete Files"
    action: file_delete
    properties:
      path: "{{delete_path}}"
      allow_absolute: true
routings:
  - from: check_trust
    to: delete_files
    condition: route_name
    name: "proceed"
  - from: check_trust
    to: request_approval
    condition: route_name
    name: "approve"
  - from: request_approval
    to: delete_files
"""

PROTECTED_PREFIX = "/etc/zebra"


def _path_judging_provider():
    """Mock LLM provider that classifies deletes under PROTECTED_PREFIX as irreversible."""
    import json as _json
    from unittest.mock import AsyncMock, MagicMock

    async def _complete(messages, **kwargs):
        prompt = messages[1].content
        irreversible = PROTECTED_PREFIX in prompt
        return MagicMock(
            content=_json.dumps(
                {
                    "reversible": not irreversible,
                    "reasoning": "protected path" if irreversible else "temp path",
                    "confidence": 0.95,
                    "chain_notes": "none",
                }
            )
        )

    provider = MagicMock()
    provider.complete = AsyncMock(side_effect=_complete)
    return provider


def _make_assessed_engine() -> WorkflowEngine:
    from zebra_tasks.filesystem.delete import FileDeleteAction

    registry = ActionRegistry()
    registry.register_action("trust_gate", TrustGateAction)
    registry.register_action("file_delete", FileDeleteAction)
    registry.register_condition("route_name", RouteNameCondition)
    return WorkflowEngine(
        InMemoryStore(),
        registry,
        extras={"__trust_store__": FakeTrustStore("SEMI_AUTONOMOUS")},
    )


async def test_protected_path_delete_classified_irreversible_forces_gate():
    """Issue #14: file delete under a protected prefix forces the trust gate."""
    from unittest.mock import patch

    engine = _make_assessed_engine()
    definition = load_definition_from_yaml(ASSESSED_WORKFLOW_YAML)

    with patch(
        "zebra_tasks.agent.reversibility.get_provider",
        return_value=_path_judging_provider(),
    ):
        process = await engine.create_process(
            definition,
            properties={"__user_id__": 1, "delete_path": f"{PROTECTED_PREFIX}/prod.conf"},
        )
        await engine.start_process(process.id)

    process = await engine.store.load_process(process.id)
    assert process.state == ProcessState.RUNNING  # paused at approval

    pending = await engine.get_pending_tasks(process.id)
    assert [t.task_definition_id for t in pending] == ["request_approval"]

    assessment = process.properties["__trust_assessments__"][0]
    assert assessment["reversible"] is False
    assert assessment["source"] == "llm"
    decision = process.properties[DECISIONS_KEY][0]
    assert decision["route"] == "approve"
    assert decision["assessment"] == assessment


async def test_temp_path_delete_classified_reversible_proceeds(tmp_path):
    """Reversible temp-path delete proceeds without approval and actually deletes."""
    from unittest.mock import patch

    victim = tmp_path / "scratch.txt"
    victim.write_text("temp data")

    engine = _make_assessed_engine()
    definition = load_definition_from_yaml(ASSESSED_WORKFLOW_YAML)

    with patch(
        "zebra_tasks.agent.reversibility.get_provider",
        return_value=_path_judging_provider(),
    ):
        process = await engine.create_process(
            definition, properties={"__user_id__": 1, "delete_path": str(victim)}
        )
        await engine.start_process(process.id)

    process = await engine.store.load_process(process.id)
    assert process.state == ProcessState.COMPLETE
    assert not victim.exists()

    pending = await engine.get_pending_tasks(process.id)
    assert pending == []
    assert process.properties["__trust_assessments__"][0]["reversible"] is True


# =============================================================================
# F16: emergency override (issue #16 e2e criterion)
# =============================================================================

# A workflow that gates the "code" domain twice with a checkpoint pause in
# between, so the emergency override can fire mid-flight and the second gate
# observes the demotion (the authentic REQ-TRUST-005 scenario).
TWO_GATE_WORKFLOW_YAML = """
id: two_gate
name: "Two Gate"
first_task_id: gate_one
tasks:
  gate_one:
    name: "Gate One"
    action: trust_gate
    properties:
      domain: "code"
      output_key: gate_one_decision
  checkpoint:
    name: "Checkpoint"
    auto: false
  gate_two:
    name: "Gate Two"
    action: trust_gate
    properties:
      domain: "code"
      output_key: gate_two_decision
  approve_two:
    name: "Approve Two"
    auto: false
  done:
    name: "Done"
    action: recording
routings:
  - {from: gate_one, to: checkpoint, condition: route_name, name: "proceed"}
  - {from: gate_one, to: checkpoint, condition: route_name, name: "approve"}
  - {from: checkpoint, to: gate_two}
  - {from: gate_two, to: done, condition: route_name, name: "proceed"}
  - {from: gate_two, to: approve_two, condition: route_name, name: "approve"}
  - {from: approve_two, to: done}
"""


async def test_emergency_override_forces_approval_on_next_gate():
    """Issue #16: a mid-flight override makes the next gate of a running workflow
    require approval, even though the workflow began while the domain was AUTONOMOUS."""
    from zebra_agent.storage.trust import InMemoryTrustStore, TrustLevel

    trust_store = InMemoryTrustStore()
    await trust_store.initialize()
    await trust_store.set_trust_level(1, "code", TrustLevel.AUTONOMOUS, "earned", "ben")

    registry = ActionRegistry()
    registry.register_action("trust_gate", TrustGateAction)
    registry.register_action("recording", RecordingAction)
    registry.register_condition("route_name", RouteNameCondition)
    engine = WorkflowEngine(InMemoryStore(), registry, extras={"__trust_store__": trust_store})
    definition = load_definition_from_yaml(TWO_GATE_WORKFLOW_YAML)

    process = await engine.create_process(definition, properties={"__user_id__": 1})
    await engine.start_process(process.id)

    # Gate one ran while code was AUTONOMOUS and proceeded; the workflow is now
    # paused at the checkpoint human task.
    process = await engine.store.load_process(process.id)
    assert process.properties["gate_one_decision"]["route"] == "proceed"
    pending = await engine.get_pending_tasks(process.id)
    assert [t.task_definition_id for t in pending] == ["checkpoint"]

    # The human triggers the emergency override while the workflow is paused.
    reverted = await trust_store.pause_all(1, "stop everything", "ben")
    assert reverted == ["code"]

    # Resuming the workflow: the second gate observes SUPERVISED and now requires
    # approval — the previously-autonomous run is stopped at its next step.
    await engine.complete_task(pending[0].id, TaskResult.ok(output={}))

    process = await engine.store.load_process(process.id)
    assert process.properties["gate_two_decision"]["level"] == "SUPERVISED"
    assert process.properties["gate_two_decision"]["route"] == "approve"
    assert process.state == ProcessState.RUNNING
    pending = await engine.get_pending_tasks(process.id)
    assert [t.task_definition_id for t in pending] == ["approve_two"]


# =============================================================================
# F17: freeing bypasses the gate (REQ-TRUST-006)
# =============================================================================


async def test_freed_user_bypasses_gate_even_when_supervised():
    """A freed user's workflow proceeds through a gate whose domain is SUPERVISED."""
    from datetime import timedelta

    from zebra_agent.storage.trust import InMemoryTrustStore, TrustLevel, list_domains

    trust_store = InMemoryTrustStore(cooling_off=timedelta(0))
    await trust_store.initialize()
    # All domains AUTONOMOUS, then freed.
    for domain in list_domains():
        await trust_store.set_trust_level(1, domain, TrustLevel.AUTONOMOUS, "earned", "ben")
    await trust_store.initiate_freeing(1, "ben")
    await trust_store.confirm_freeing(1, "ben")
    # Demoting after freeing is inert at the gate (and pause_all is a no-op).
    assert await trust_store.pause_all(1, "try to stop", "ben") == []

    registry = ActionRegistry()
    registry.register_action("trust_gate", TrustGateAction)
    registry.register_action("recording", RecordingAction)
    registry.register_condition("route_name", RouteNameCondition)
    engine = WorkflowEngine(InMemoryStore(), registry, extras={"__trust_store__": trust_store})
    definition = load_definition_from_yaml(GATED_WORKFLOW_YAML)

    process = await engine.create_process(definition, properties={"__user_id__": 1})
    await engine.start_process(process.id)

    process = await engine.store.load_process(process.id)
    assert process.state == ProcessState.COMPLETE
    assert RecordingAction.executed == 1
    assert process.properties[DECISIONS_KEY][0]["level"] == "FREED"
    assert process.properties[DECISIONS_KEY][0]["route"] == "proceed"
