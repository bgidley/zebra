"""Commons S0 safety prerequisites (#245): choke point, hints, strict gym mode.

The test that refusing at the choke point stops every entry point lives in
``zebra-agent/tests/test_launch_choke_point.py`` (it needs the agent loop,
direct runs and the scheduler).
"""

import re
from importlib.metadata import entry_points
from pathlib import Path

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessDefinition, ProcessState, TaskDefinition
from zebra.storage.memory import InMemoryStore
from zebra.tasks.actions import get_default_actions
from zebra.tasks.base import TaskAction
from zebra.tasks.registry import ActionRegistry

from zebra_tasks import launch
from zebra_tasks.agent.gym import unsafe_reason
from zebra_tasks.launch import LAUNCH_ENTRIES, LaunchRefused, create_library_process

REPO = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# The choke point itself
# ---------------------------------------------------------------------------


def _definition(*actions: str) -> ProcessDefinition:
    tasks = {
        f"t{i}": TaskDefinition(id=f"t{i}", name=f"T{i}", action=a) for i, a in enumerate(actions)
    }
    return ProcessDefinition(
        id="wf", name="Wf", first_task_id="t0" if tasks else "", tasks=tasks, routings=[]
    )


async def test_check_launch_allows_every_entry_today():
    for entry in LAUNCH_ENTRIES:
        assert await launch.check_launch(_definition("shell"), entry=entry, properties={}) is None


async def test_create_library_process_creates_when_allowed():
    engine = WorkflowEngine(InMemoryStore(), ActionRegistry())
    process = await create_library_process(
        engine, _definition("shell"), entry="goal", properties={"goal": "x"}
    )
    assert process.state == ProcessState.CREATED
    assert process.properties == {"goal": "x"}


async def test_create_library_process_refused_creates_nothing(monkeypatch):
    seen: list[tuple[str, dict]] = []

    async def refuse(definition, *, entry, properties):
        seen.append((entry, properties))
        raise LaunchRefused("not approved")

    monkeypatch.setattr(launch, "check_launch", refuse)
    store = InMemoryStore()
    engine = WorkflowEngine(store, ActionRegistry())
    with pytest.raises(LaunchRefused, match="not approved"):
        await create_library_process(engine, _definition("shell"), entry="routine")
    assert seen == [("routine", {})]
    assert await store.get_processes_by_state(ProcessState.CREATED) == []


async def test_unknown_entry_is_rejected():
    engine = WorkflowEngine(InMemoryStore(), ActionRegistry())
    with pytest.raises(ValueError, match="Unknown launch entry"):
        await create_library_process(engine, _definition("shell"), entry="somewhere")


# ---------------------------------------------------------------------------
# Nothing creates a process around the choke point unnoticed
# ---------------------------------------------------------------------------

# Production ``create_process(`` calls outside launch.py, with why each may skip it.
# A new entry point must either use create_library_process or be added here with
# a reason. Counts are per file.
ALLOWED_CREATE_PROCESS = {
    "zebra-py/zebra/core/engine.py": (
        2,
        "docstring example; create_replay re-runs a recorded process for a human debugging it",
    ),
    "zebra-tasks/zebra_tasks/launch.py": (1, "the choke point itself"),
    "zebra-tasks/zebra_tasks/agent/gym.py": (
        1,
        "the gym's own sandboxed runs, gated by unsafe_reason (strict mode for imports)",
    ),
    "zebra-tasks/zebra_tasks/agent/improvements.py": (1, "built-in Zebra Improvement Request"),
    "zebra-tasks/zebra_tasks/agent/queue_goal.py": (
        1,
        "queues the Agent Main Loop; its goal workflow launches via execute_goal_workflow",
    ),
    "zebra-tasks/zebra_tasks/knowledge/review.py": (1, "built-in knowledge review workflows"),
    "zebra-tasks/zebra_tasks/knowledge/store_learned.py": (
        1,
        "built-in Resolve Knowledge Contradiction",
    ),
    "zebra-agent/zebra_agent/postmortem.py": (1, "built-in Postmortem"),
    "zebra-agent-web/zebra_agent_web/api/goals.py": (
        1,
        "queues the Agent Main Loop; its goal workflow launches via execute_goal_workflow",
    ),
    "zebra-agent-web/zebra_agent_web/api/web_views.py": (
        2,
        "built-in Values Profile Wizard and Bug Report",
    ),
}

_PACKAGES = [
    "zebra-py/zebra",
    "zebra-tasks/zebra_tasks",
    "zebra-agent/zebra_agent",
    "zebra-agent-web/zebra_agent_web",
]


def _create_process_calls() -> dict[str, int]:
    counts: dict[str, int] = {}
    pattern = re.compile(r"\bcreate_process\(")
    for package in _PACKAGES:
        for path in (REPO / package).rglob("*.py"):
            if "migrations" in path.parts or "tests" in path.parts:
                continue
            text = "\n".join(
                line
                for line in path.read_text().splitlines()
                if not line.lstrip().startswith(("def create_process", "async def create_process"))
            )
            found = len(pattern.findall(text))
            if found:
                counts[path.relative_to(REPO).as_posix()] = found
    return counts


def test_no_create_process_call_bypasses_the_choke_point():
    calls = _create_process_calls()
    allowed = {path: count for path, (count, _reason) in ALLOWED_CREATE_PROCESS.items()}
    assert calls == allowed, (
        "A create_process call was added or removed outside zebra_tasks/launch.py. Start "
        "library workflows with create_library_process, or allowlist the call with a reason."
    )


# ---------------------------------------------------------------------------
# Every action declares an honest reversibility hint
# ---------------------------------------------------------------------------


def _registered_actions() -> dict[str, type[TaskAction]]:
    actions = dict(get_default_actions())
    for ep in entry_points(group="zebra.tasks"):
        actions[ep.name] = ep.load()
    return actions


ACTIONS = _registered_actions()

# Actions that write outside the run (files, stores, library, goal queue, child
# workflows, code). None may be always_reversible, or strict mode would run them.
WRITERS = {
    "shell",
    "python_exec",
    "file_write",
    "file_copy",
    "file_move",
    "file_delete",
    "subworkflow",
    "parallel_subworkflows",
    "execute_goal_workflow",
    "queue_goal",
    "add_knowledge",
    "store_learned_knowledge",
    "apply_resolution",
    "apply_verification_result",
    "decay_confidence",
    "save_values_profile",
    "update_conceptual_memory",
    "compact_memory",
    "assess_and_record",
    "record_metrics",
    "propose_trust_promotion",
    "workflow_creator",
    "workflow_variant_creator",
    "workflow_optimizer",
    "run_golden_gym",
    "llm_agent",
}


def test_registry_is_not_empty():
    assert {"file_delete", "shell", "llm_call", "queue_goal"} <= set(ACTIONS)


@pytest.mark.parametrize("name", sorted(ACTIONS))
def test_action_declares_its_own_hint(name):
    cls = ACTIONS[name]
    declared = any(
        "reversibility_hint" in vars(klass) for klass in cls.__mro__ if klass is not TaskAction
    )
    assert declared, f"{name} ({cls.__qualname__}) relies on the default reversibility hint"
    assert cls.reversibility_hint in {
        "always_reversible",
        "always_irreversible",
        "context_dependent",
    }


@pytest.mark.parametrize("name", sorted(WRITERS))
def test_writers_are_not_always_reversible(name):
    assert ACTIONS[name].reversibility_hint != "always_reversible"


# ---------------------------------------------------------------------------
# Strict gym mode
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def registry() -> ActionRegistry:
    reg = ActionRegistry()
    for name, cls in ACTIONS.items():
        reg.register_action(name, cls)
    return reg


def test_file_delete_passes_gate_mode_but_not_strict(registry):
    definition = _definition("llm_call", "file_delete")
    assert unsafe_reason(definition, registry) is None
    reason = unsafe_reason(definition, registry, strict=True)
    assert reason == "action 'file_delete' is not always reversible (context_dependent)"


def test_pure_workflow_passes_strict_mode(registry):
    definition = _definition("llm_call", "transform_json", "file_read")
    assert unsafe_reason(definition, registry, strict=True) is None


def test_strict_mode_keeps_the_gate_rules(registry):
    assert unsafe_reason(_definition("http_request"), registry, strict=True) == (
        "action 'http_request' is irreversible"
    )
    assert unsafe_reason(_definition("no_such_action"), registry, strict=True) == (
        "action 'no_such_action' is not registered"
    )


@pytest.mark.parametrize("name", sorted(ACTIONS))
def test_strict_mode_passes_exactly_the_always_reversible_actions(registry, name):
    reason = unsafe_reason(_definition(name), registry, strict=True)
    if ACTIONS[name].reversibility_hint == "always_reversible":
        assert reason is None
    else:
        assert reason is not None and name in reason
