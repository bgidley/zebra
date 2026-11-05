"""Supervised use of imported workflows at the launch choke point (Commons S3, #230).

An adopted workflow (``commons.supervised``) never starts directly: every entry point
gets a *Supervised run* wrapper whose owner-only approval task must say ``run`` before
the real workflow has a process. Rejecting a goal's run fails over to another workflow;
the flag clears after ``SUPERVISED_RUNS`` approved successful runs or an owner clear;
a stopped Commons refuses the launch.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState, TaskInstance, TaskResult
from zebra.definitions.loader import load_definition_from_yaml
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import ExecutionContext, TaskAction
from zebra.tasks.registry import ActionRegistry
from zebra_tasks.agent.execute_workflow import (
    EXCLUDED_WORKFLOWS_KEY,
    ExecuteGoalWorkflowAction,
)
from zebra_tasks.commons.supervised import (
    APPROVAL_TASK,
    SUPERVISED_LAUNCH_KEY,
    SUPERVISED_REJECTED_KEY,
    WRAPPER_NAME_PREFIX,
    CommonsSupervisedRunAction,
    is_reserved_name,
    supervision_for,
)
from zebra_tasks.launch import LaunchRefused, check_launch, create_library_process
from zebra_tasks.llm.agent import LLMAgentAction, tool_slug
from zebra_tasks.llm.base import LLMProvider, LLMResponse, TokenUsage, ToolCall
from zebra_tasks.llm.client import set_llm_factory
from zebra_tasks.subtasks import ParallelSubworkflowsAction, SubworkflowAction

from zebra_agent.direct_run import run_named_workflow
from zebra_agent.library import SUPERVISED_RUNS, AdoptionRefused, WorkflowLibrary
from zebra_agent.provenance import read_commons, relabel
from zebra_agent.scheduler.loop import SchedulerLoop
from zebra_agent.scheduler.registry import RoutineRegistry
from zebra_agent.scheduler.routine import Routine, RoutineRun
from zebra_agent.scheduler.store import InMemoryRoutineRunStore
from zebra_agent.scheduler.testing import FakeClock

SHARED = "Shared Tool (from Pub)"

SHARED_YAML = """
name: "Shared Tool"
description: "A workflow another Zebra shared."
tags: ["misc"]
first_task: work
tasks:
  work:
    name: "Work"
    action: ok
    properties: {output_key: answer}
  wipe:
    name: "Wipe"
    action: wipe
routings:
  - {from: work, to: wipe}
"""

LOCAL_YAML = """
name: "Local Tool"
description: "Learnt here."
tags: ["misc"]
first_task: work
tasks:
  work:
    name: "Work"
    action: ok
"""


class _OkAction(TaskAction):
    reversibility_hint = "always_reversible"

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        context.set_process_property(task.properties.get("output_key", "result"), "done")
        return TaskResult.ok(output="done")


class _WipeAction(TaskAction):
    reversibility_hint = "always_irreversible"

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        return TaskResult.ok(output="wiped")


class _ScriptedProvider(LLMProvider):
    """Calls one tool, then answers."""

    def __init__(self, tool: str) -> None:
        call = ToolCall(id="call_1", name=tool, arguments={"goal": "x"})
        usage = TokenUsage(10, 5)
        self.replies = [
            LLMResponse("", [call], "tool_use", usage, "test/model"),
            LLMResponse("no tool ran", None, "end_turn", usage, "test/model"),
        ]

    async def complete(self, messages, tools=None, temperature=0.7, max_tokens=4096, **kw):
        return self.replies.pop(0)

    async def stream(self, messages, tools=None, temperature=0.7, max_tokens=4096):
        raise NotImplementedError
        yield ""

    @property
    def name(self) -> str:
        return "scripted"

    @property
    def model(self) -> str:
        return "test/model"

    @property
    def max_context_tokens(self) -> int:
        return 200_000


class _StoppedCommons:
    async def stop_reason(self) -> str:
        return "the kill switch is on"


def adopt(library: WorkflowLibrary, tmp_path: Path, yaml_text: str, name: str) -> None:
    """Adopt *yaml_text* as *name*, as ``commons_adopt`` does."""
    publisher = WorkflowLibrary(tmp_path / "publisher", owner_user_id=1)
    publisher.add_workflow(yaml_text)
    text = next(publisher.library_path.glob("*.yaml")).read_text()
    block = read_commons(text)
    library.save(
        relabel(text),
        writer="adopt",
        received=block,
        expected_sha256=block["content_sha256"],
        name=name,
        origin_pubkey="ab" * 32,
    )


@pytest.fixture
def library(tmp_path: Path) -> WorkflowLibrary:
    lib = WorkflowLibrary(tmp_path / "workflows", owner_user_id=1)
    lib.ensure_initialized()
    adopt(lib, tmp_path, SHARED_YAML, SHARED)
    lib.add_workflow(LOCAL_YAML)
    return lib


@pytest.fixture
def engine(library: WorkflowLibrary) -> WorkflowEngine:
    registry = ActionRegistry()
    registry.register_defaults()
    registry.register_action("ok", _OkAction)
    registry.register_action("wipe", _WipeAction)
    registry.register_action("execute_goal_workflow", ExecuteGoalWorkflowAction)
    registry.register_action("subworkflow", SubworkflowAction)
    registry.register_action("parallel_subworkflows", ParallelSubworkflowsAction)
    registry.register_action("llm_agent", LLMAgentAction)
    registry.register_action("commons_supervised_run", CommonsSupervisedRunAction)
    return WorkflowEngine(InMemoryStore(), registry, extras={"__workflow_library__": library})


@pytest.fixture
def created(engine: WorkflowEngine) -> list[str]:
    names: list[str] = []
    original = engine.create_process

    async def recording(definition, *args, **kwargs):
        names.append(definition.name)
        return await original(definition, *args, **kwargs)

    engine.create_process = recording
    return names


async def _run_parent(engine: WorkflowEngine, yaml: str):
    process = await engine.create_process(load_definition_from_yaml(yaml))
    await engine.start_process(process.id)
    return await engine.store.load_process(process.id)


async def _wrappers(engine: WorkflowEngine) -> list:
    found = []
    for state in ProcessState:
        for p in await engine.store.get_processes_by_state(state):
            if SUPERVISED_LAUNCH_KEY in (p.properties or {}):
                found.append(p)
    return found


async def _answer(engine: WorkflowEngine, wrapper_id: str, decision: str) -> None:
    pending = await engine.get_pending_tasks(wrapper_id)
    assert [t.task_definition_id for t in pending] == [APPROVAL_TASK]
    await engine.complete_task(pending[0].id, TaskResult.ok(output={"decision": decision}))


GOAL_PARENT = f"""
name: Goal
first_task_id: execute
tasks:
  execute:
    name: Execute
    action: execute_goal_workflow
    properties: {{workflow_name: "{SHARED}", goal: do it, continue_on_failure: true}}
  done:
    name: Done
    action: ok
  reselect:
    name: Reselect
    action: ok
routings:
  - {{from: execute, to: done, condition: route_name}}
  - {{from: execute, to: reselect, condition: route_name, name: supervision_rejected}}
"""


# ---------------------------------------------------------------------------
# The choke point
# ---------------------------------------------------------------------------


async def test_check_launch_flags_only_supervised_workflows(library, engine):
    assert library.is_supervised(SHARED) is True
    assert library.is_supervised("Local Tool") is False
    extras = engine.extras
    local = library.get_workflow("Local Tool")
    assert await check_launch(local, entry="goal", properties={}, extras=extras) is None
    launch = await check_launch(
        library.get_workflow(SHARED),
        entry="goal",
        properties={},
        extras=extras,
        registry=engine.actions,
    )
    flags = {a["action"]: a["flag"] for a in launch.actions}
    assert flags == {"ok": "", "wipe": "irreversible"}


async def test_stopped_commons_refuses_supervised_launch_only(library, engine, created):
    engine.extras["__commons__"] = _StoppedCommons()
    with pytest.raises(LaunchRefused, match="kill switch"):
        await create_library_process(engine, library.get_workflow(SHARED), entry="routine")
    process = await create_library_process(
        engine, library.get_workflow("Local Tool"), entry="routine"
    )
    assert created == ["Local Tool"] and process.state == ProcessState.CREATED


async def test_goal_parks_on_approval_then_runs_and_counts(library, engine, created):
    parent = await _run_parent(engine, GOAL_PARENT)
    assert parent.state == ProcessState.RUNNING
    assert created == ["Goal", WRAPPER_NAME_PREFIX + SHARED]  # the real one has no process yet
    [wrapper] = await _wrappers(engine)
    assert wrapper.parent_process_id == parent.id
    summary = wrapper.properties["supervised_summary"]
    assert "`wipe` — **irreversible**" in summary and "Goal: do it" in summary
    approval = (await engine.store.load_definition(wrapper.definition_id)).tasks[APPROVAL_TASK]
    assert approval.properties["owner_only"] is True

    await _answer(engine, wrapper.id, "run")
    parent = await engine.store.load_process(parent.id)
    assert parent.state == ProcessState.COMPLETE
    assert created[-1] == SHARED
    result = parent.properties["execution_result"]
    assert result["success"] is True and result["output"] == "done"
    assert "__task_output_done" in parent.properties
    assert library.is_supervised(SHARED) is True  # one approved run of three


async def test_rejected_goal_run_fails_over(library, engine, created):
    parent = await _run_parent(engine, GOAL_PARENT)
    [wrapper] = await _wrappers(engine)
    await _answer(engine, wrapper.id, "reject")
    parent = await engine.store.load_process(parent.id)
    wrapper = await engine.store.load_process(wrapper.id)
    assert wrapper.state == ProcessState.FAILED
    assert wrapper.properties[SUPERVISED_REJECTED_KEY]["workflow"] == SHARED
    assert SHARED not in created  # nothing of it ran
    assert parent.properties[EXCLUDED_WORKFLOWS_KEY] == [SHARED]
    assert "__task_output_reselect" in parent.properties
    assert "__task_output_done" not in parent.properties


async def test_failed_or_rejected_runs_do_not_count(library, engine):
    await _run_parent(engine, GOAL_PARENT)
    [wrapper] = await _wrappers(engine)
    await _answer(engine, wrapper.id, "reject")
    assert library._supervision_counts() == {}
    assert library.is_supervised(SHARED) is True


async def test_routine_start_raises_the_approval(library, engine, created):
    start = datetime(2026, 11, 4, 3, 0, tzinfo=UTC)
    registry = RoutineRegistry()
    registry.register(Routine(name="nightly", schedule={"every": "1m"}, workflow=SHARED))
    store = InMemoryRoutineRunStore()
    await store.upsert_run(RoutineRun("nightly", last_run=None, next_run=start - timedelta(1)))
    loop = SchedulerLoop(registry=registry, store=store, engine=engine, clock=FakeClock(start))
    await loop._tick()
    assert created == [WRAPPER_NAME_PREFIX + SHARED]
    [wrapper] = await _wrappers(engine)
    assert wrapper.properties[SUPERVISED_LAUNCH_KEY]["entry"] == "routine"
    assert [t.task_definition_id for t in await engine.get_pending_tasks(wrapper.id)] == [
        APPROVAL_TASK
    ]


async def test_direct_run_raises_the_approval(library, engine, created):
    await run_named_workflow(engine, library, SHARED, {"goal": "x"})
    assert created == [WRAPPER_NAME_PREFIX + SHARED]


async def test_subworkflow_and_parallel_raise_one_approval_each(library, engine, created):
    filename = next(p.name for p in library.library_path.glob("*.yaml") if "pub" in p.name)
    await _run_parent(
        engine,
        f"""
name: Parent
first_task_id: spawn
tasks:
  spawn:
    name: Spawn
    action: subworkflow
    properties: {{workflow_file: "{filename}"}}
""",
    )
    # An inline copy under the adopted name is supervised too (the check is by name)
    inline = json.dumps(library.get_workflow_yaml(SHARED).strip())
    await _run_parent(
        engine,
        f"""
name: Fan
first_task_id: fan
tasks:
  fan:
    name: Fan
    action: parallel_subworkflows
    properties:
      workflows:
        - {{key: a, workflow: {inline}}}
""",
    )
    wrapper = WRAPPER_NAME_PREFIX + SHARED
    assert created == ["Parent", wrapper, "Fan", wrapper]


async def test_llm_agent_tool_raises_the_approval(library, engine, created):
    set_llm_factory(lambda model: _ScriptedProvider(tool_slug(SHARED)))
    await _run_parent(
        engine,
        f"""
name: Agent
first_task_id: agent
tasks:
  agent:
    name: Agent
    action: llm_agent
    properties: {{prompt: use the tool, tools: ["{SHARED}"]}}
""",
    )
    assert created == ["Agent", WRAPPER_NAME_PREFIX + SHARED]


async def test_ordinary_workflows_are_unaffected(library, engine, created):
    await run_named_workflow(engine, library, "Local Tool", {"goal": "x"})
    assert created == ["Local Tool"]
    assert await _wrappers(engine) == []


# ---------------------------------------------------------------------------
# Supervision state
# ---------------------------------------------------------------------------


def test_flag_clears_after_supervised_runs(library):
    block_before = library.commons_block(SHARED)
    definition_id = library.get_workflow(SHARED).id
    for n in range(1, SUPERVISED_RUNS):
        assert library.record_supervised_run(SHARED) == {"supervised": True, "runs": n}
    assert library.record_supervised_run(SHARED) == {"supervised": False, "runs": SUPERVISED_RUNS}
    assert library.is_supervised(SHARED) is False
    block = library.commons_block(SHARED)
    assert block["content_sha256"] == block_before["content_sha256"]
    assert library.get_workflow(SHARED).id == definition_id
    assert library.record_supervised_run(SHARED) == {"supervised": False, "runs": 0}


def test_owner_clear_and_emergency_resupervise(library):
    library.record_supervised_run(SHARED)
    assert library.clear_supervision(SHARED) is True
    assert library.clear_supervision(SHARED) is False
    assert library.is_supervised(SHARED) is False
    assert library.resupervise_adopted() == [SHARED]
    assert library.is_supervised(SHARED) is True
    assert library.is_supervised("Local Tool") is False
    assert library._supervision_counts() == {}


# ---------------------------------------------------------------------------
# No name dodges supervision
# ---------------------------------------------------------------------------


class _AlwaysSupervised:
    def is_supervised(self, name: str) -> bool:
        return True


@pytest.mark.parametrize("name", ["Foo (from Bob)", WRAPPER_NAME_PREFIX + "Foo (from Bob)"])
def test_supervision_for_exempts_no_name(name):
    """A workflow named like the wrapper is still supervised (the reviewer's repro)."""
    definition = load_definition_from_yaml(
        f'name: "{name}"\nfirst_task: work\ntasks:\n  work: {{name: Work, action: ok}}\n'
    )
    extras = {"__workflow_library__": _AlwaysSupervised()}
    assert supervision_for(definition, extras) is True


@pytest.mark.parametrize(
    ("name", "reserved"),
    [
        ("Supervised run: Foo", True),
        ("  supervised   RUN: Foo", True),
        ("Supervised running club", False),
        ("Foo (from Supervised run: Bob)", False),
    ],
)
def test_reserved_names(name, reserved):
    assert is_reserved_name(name) is reserved


def test_library_refuses_to_adopt_a_wrapper_like_name(library, tmp_path):
    with pytest.raises(AdoptionRefused, match="reserved"):
        adopt(library, tmp_path / "other", LOCAL_YAML, WRAPPER_NAME_PREFIX + "Local (from Pub)")
    assert library.commons_block(WRAPPER_NAME_PREFIX + "Local (from Pub)") is None


async def test_wrapper_like_supervised_workflow_still_asks_first(library, engine, created):
    """Were one in the library, its launch still goes through the wrapper."""
    name = WRAPPER_NAME_PREFIX + SHARED
    definition = library.get_workflow(SHARED).model_copy(update={"name": name})
    library.is_supervised = lambda n: n in (SHARED, name)
    launch = await check_launch(definition, entry="routine", properties={}, extras=engine.extras)
    assert launch is not None and launch.workflow == name
    process = await create_library_process(engine, definition, entry="routine")
    assert process.properties[SUPERVISED_LAUNCH_KEY]["workflow"] == name
