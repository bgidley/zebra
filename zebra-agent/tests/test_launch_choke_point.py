"""Every start of a library workflow goes through one choke point (#245, Commons S0).

Patching ``zebra_tasks.launch.check_launch`` to refuse must stop every entry point:
goals (``execute_goal_workflow``), the agent loop, the dream cycle, direct runs,
scheduled routines, ``subworkflow``, ``parallel_subworkflows`` and ``llm_agent``
tool calls. Each must create no child process and report the refusal. Also:
protected workflows are never exportable to the Commons.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessDefinition, ProcessState, TaskInstance, TaskResult
from zebra.definitions.loader import load_definition_from_yaml
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import ExecutionContext, TaskAction
from zebra.tasks.registry import ActionRegistry
from zebra_tasks import launch
from zebra_tasks.agent.execute_workflow import ExecuteGoalWorkflowAction
from zebra_tasks.launch import LaunchRefused
from zebra_tasks.llm.agent import LLMAgentAction, tool_slug
from zebra_tasks.llm.base import LLMProvider, LLMResponse, TokenUsage, ToolCall
from zebra_tasks.llm.client import set_llm_factory
from zebra_tasks.subtasks import ParallelSubworkflowsAction, SubworkflowAction

from zebra_agent.commons import commons_exportable
from zebra_agent.direct_run import DirectRunError, run_named_workflow
from zebra_agent.library import WorkflowInfo, WorkflowLibrary
from zebra_agent.loop import AgentLoop
from zebra_agent.scheduler.loop import SchedulerLoop
from zebra_agent.scheduler.registry import RoutineRegistry
from zebra_agent.scheduler.routine import Routine, RoutineRun
from zebra_agent.scheduler.store import InMemoryRoutineRunStore
from zebra_agent.scheduler.testing import FakeClock
from zebra_agent.storage.metrics import InMemoryMetricsStore

BUILTIN_WORKFLOWS = Path(__file__).resolve().parents[1] / "workflows"

CHILD_YAML = """
name: "Child Tool"
description: "A library workflow."
tags: ["misc"]
first_task: work
tasks:
  work:
    name: "Work"
    action: ok
"""

INLINE_CHILD = (
    "{id: inline, name: Inline, first_task_id: only,"
    " tasks: {only: {id: only, name: Only, action: ok}}, routings: []}"
)


class _OkAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        return TaskResult.ok(output="done")


class _ScriptedProvider(LLMProvider):
    """Calls one tool, then answers."""

    def __init__(self, tool: str) -> None:
        self.replies = [
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="call_1", name=tool, arguments={"goal": "x"})],
                finish_reason="tool_use",
                usage=TokenUsage(10, 5),
                model="test/model",
            ),
            LLMResponse(
                content="no tool ran",
                tool_calls=None,
                finish_reason="end_turn",
                usage=TokenUsage(10, 5),
                model="test/model",
            ),
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


@pytest.fixture
def library(tmp_path: Path) -> WorkflowLibrary:
    lib = WorkflowLibrary(tmp_path / "workflows")
    lib.ensure_initialized()
    lib.copy_builtin_workflows(BUILTIN_WORKFLOWS)
    (lib.library_path / "child_tool.yaml").write_text(CHILD_YAML)
    return lib


@pytest.fixture
def engine(library: WorkflowLibrary) -> WorkflowEngine:
    registry = ActionRegistry()
    registry.register_defaults()
    registry.register_action("ok", _OkAction)
    registry.register_action("execute_goal_workflow", ExecuteGoalWorkflowAction)
    registry.register_action("subworkflow", SubworkflowAction)
    registry.register_action("parallel_subworkflows", ParallelSubworkflowsAction)
    registry.register_action("llm_agent", LLMAgentAction)
    return WorkflowEngine(InMemoryStore(), registry, extras={"__workflow_library__": library})


@pytest.fixture
def refusals(monkeypatch) -> list[str]:
    """Make the choke point refuse every launch; record which entry asked."""
    entries: list[str] = []

    async def refuse(
        definition: ProcessDefinition, *, entry: str, properties: dict, **_: object
    ) -> None:
        entries.append(entry)
        raise LaunchRefused(f"{definition.name} is not approved")

    monkeypatch.setattr(launch, "check_launch", refuse)
    return entries


@pytest.fixture
def created(engine: WorkflowEngine) -> list[str]:
    """Names of every workflow the engine creates a process for."""
    names: list[str] = []
    original = engine.create_process

    async def recording(definition, *args, **kwargs):
        names.append(definition.name)
        return await original(definition, *args, **kwargs)

    engine.create_process = recording
    return names


async def _run_parent(engine: WorkflowEngine, yaml: str):
    definition = load_definition_from_yaml(yaml)
    process = await engine.create_process(definition)
    await engine.start_process(process.id)
    return await engine.store.load_process(process.id)


# ---------------------------------------------------------------------------
# Task-action entry points: the parent runs, the refused child never exists
# ---------------------------------------------------------------------------


async def test_goal_execute_workflow_refused(engine, refusals, created):
    parent = await _run_parent(
        engine,
        """
name: Goal
first_task_id: execute
tasks:
  execute:
    name: Execute
    action: execute_goal_workflow
    properties: {workflow_name: Child Tool, goal: do it}
""",
    )
    assert refusals == ["goal"]
    assert created == ["Goal"]
    assert parent.state == ProcessState.FAILED
    assert "not approved" in parent.properties["execution_result"]["error"]


async def test_subworkflow_refused(engine, refusals, created):
    parent = await _run_parent(
        engine,
        f"""
name: Parent
first_task_id: spawn
tasks:
  spawn:
    name: Spawn
    action: subworkflow
    properties:
      workflow: {INLINE_CHILD}
""",
    )
    assert refusals == ["subworkflow"]
    assert created == ["Parent"]
    assert parent.state == ProcessState.FAILED


async def test_parallel_subworkflows_refused(engine, refusals, created):
    parent = await _run_parent(
        engine,
        f"""
name: Parent
first_task_id: fan_out
tasks:
  fan_out:
    name: Fan out
    action: parallel_subworkflows
    properties:
      workflows:
        - {{key: a, workflow: {INLINE_CHILD}}}
        - {{key: b, workflow: {INLINE_CHILD}}}
""",
    )
    assert refusals == ["parallel_subworkflows", "parallel_subworkflows"]
    assert created == ["Parent"]
    results = parent.properties["parallel_results"]
    assert set(results) == {"a", "b"}
    assert all(r["success"] is False and "not approved" in r["error"] for r in results.values())


async def test_parallel_fail_fast_stops_at_first_refusal(engine, refusals, created):
    await _run_parent(
        engine,
        f"""
name: Parent
first_task_id: fan_out
tasks:
  fan_out:
    name: Fan out
    action: parallel_subworkflows
    properties:
      fail_fast: true
      workflows:
        - {{key: a, workflow: {INLINE_CHILD}}}
        - {{key: b, workflow: {INLINE_CHILD}}}
""",
    )
    assert refusals == ["parallel_subworkflows"]
    assert created == ["Parent"]


async def test_llm_agent_tool_refused(engine, refusals, created):
    provider = _ScriptedProvider(tool_slug("Child Tool"))
    set_llm_factory(lambda model: provider)
    parent = await _run_parent(
        engine,
        """
name: Agent
first_task_id: agent
tasks:
  agent:
    name: Agent
    action: llm_agent
    properties:
      prompt: use the tool
      tools: ["Child Tool"]
""",
    )
    assert refusals == ["llm_agent_tool"]
    assert created == ["Agent"]
    assert parent.state == ProcessState.COMPLETE
    transcript = parent.properties["__task_output_agent"]["transcript"]
    assert transcript[0]["process_id"] is None
    assert "Launch refused" in transcript[0]["result"]


# ---------------------------------------------------------------------------
# zebra-agent entry points
# ---------------------------------------------------------------------------


async def test_agent_loop_goal_refused(engine, library, refusals, created):
    loop = AgentLoop(library=library, engine=engine, metrics=InMemoryMetricsStore())
    definition = library.get_workflow("Agent Main Loop")
    with pytest.raises(LaunchRefused):
        await loop._run_agent_workflow(definition, {"goal": "g"}, "g", "run-1")
    assert refusals == ["agent_loop"]
    assert created == []


async def test_dream_cycle_refused(engine, library, refusals, created):
    loop = AgentLoop(library=library, engine=engine, metrics=InMemoryMetricsStore())
    with pytest.raises(LaunchRefused):
        await loop.run_dream_cycle()
    assert refusals == ["dream_cycle"]
    assert created == []


async def test_direct_run_refused(engine, library, refusals, created):
    with pytest.raises(DirectRunError, match="refused"):
        await run_named_workflow(engine, library, "Child Tool", {"goal": "x"})
    assert refusals == ["direct_run"]
    assert created == []


async def test_scheduled_routine_refused(engine, refusals, created):
    start = datetime(2026, 10, 30, 3, 0, tzinfo=UTC)
    registry = RoutineRegistry()
    registry.register(Routine(name="nightly", schedule={"every": "1m"}, workflow="Child Tool"))
    store = InMemoryRoutineRunStore()
    await store.upsert_run(RoutineRun("nightly", last_run=None, next_run=start - timedelta(1)))
    loop = SchedulerLoop(registry=registry, store=store, engine=engine, clock=FakeClock(start))
    await loop._tick()
    assert refusals == ["routine"]
    assert created == []
    assert (await store.get_run("nightly")).last_status == "refused"


async def test_default_hook_lets_every_entry_start(engine, library, created):
    """With the real (no-op) hook, the same paths create their children."""
    await run_named_workflow(engine, library, "Child Tool", {"goal": "x"})
    await _run_parent(
        engine,
        f"""
name: Parent
first_task_id: spawn
tasks:
  spawn:
    name: Spawn
    action: subworkflow
    properties:
      workflow: {INLINE_CHILD}
""",
    )
    assert created == ["Child Tool", "Parent", "Inline"]


# ---------------------------------------------------------------------------
# Protected workflows never leave the deployment
# ---------------------------------------------------------------------------


async def test_protected_workflows_are_not_exportable(library):
    infos = {info.name: info for info in await library.list_workflows()}
    assert commons_exportable(infos["Agent Main Loop"]) is False
    assert commons_exportable(infos["Dream Cycle"]) is False
    system_tagged = [i for i in infos.values() if "system" in i.tags]
    assert system_tagged and not any(commons_exportable(i) for i in system_tagged)
    # Written straight to disk: no commons block, unknown lineage (#229)
    assert commons_exportable(infos["Child Tool"]) is False
    library.add_workflow(CHILD_YAML.replace("Child Tool", "Saved Tool"))
    infos = {info.name: info for info in await library.list_workflows()}
    assert commons_exportable(infos["Saved Tool"]) is True


def test_system_name_is_protected_even_without_the_tag():
    info = WorkflowInfo(
        name="Dream Cycle", description="", tags=[], version=1, definition_path=Path("x.yaml")
    )
    assert commons_exportable(info) is False
