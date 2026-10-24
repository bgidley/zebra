"""Child processes are linked to their parent from their first save (#227).

The daemon's goal queue starts every CREATED process with no parent. A child saved
before its parent link was set could be picked up in that gap and started a second
time, leaving a duplicate first task stuck behind a ``LockError``. These tests watch
every save the way the queue would and check no child is ever offered as a goal.
"""

from unittest.mock import MagicMock

from zebra.core.engine import WorkflowEngine
from zebra.core.models import (
    ProcessDefinition,
    ProcessEventKind,
    ProcessInstance,
    ProcessState,
    TaskDefinition,
    TaskInstance,
    TaskResult,
)
from zebra.definitions.loader import load_definition_from_yaml
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import ExecutionContext, TaskAction
from zebra.tasks.registry import ActionRegistry

from zebra_tasks.agent.execute_workflow import ExecuteGoalWorkflowAction
from zebra_tasks.subtasks import ParallelSubworkflowsAction, SubworkflowAction


class _QueueWatchingStore(InMemoryStore):
    """Records the first saved state of each process and what the goal queue saw."""

    def __init__(self) -> None:
        super().__init__()
        self.first_saves: dict[str, ProcessInstance] = {}
        self.queued_ids: set[str] = set()

    async def save_process(self, process: ProcessInstance) -> None:
        await super().save_process(process)
        self.first_saves.setdefault(process.id, process.model_copy(deep=True))
        # The query GoalScheduler.get_pending_goals() runs on every daemon tick.
        pending = await self.get_processes_by_state(ProcessState.CREATED, exclude_children=True)
        self.queued_ids.update(p.id for p in pending)


class _OkAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        return TaskResult.ok(output="done")


CHILD = ProcessDefinition(
    id="child",
    name="Child",
    first_task_id="count",
    tasks={"count": TaskDefinition(id="count", name="Count", action="ok")},
    routings=[],
)


def _engine() -> WorkflowEngine:
    registry = ActionRegistry()
    registry.register_defaults()
    registry.register_action("ok", _OkAction)
    registry.register_action("execute_goal_workflow", ExecuteGoalWorkflowAction)
    registry.register_action("subworkflow", SubworkflowAction)
    registry.register_action("parallel_subworkflows", ParallelSubworkflowsAction)
    library = MagicMock()
    library.get_workflow.return_value = CHILD
    return WorkflowEngine(_QueueWatchingStore(), registry, extras={"__workflow_library__": library})


async def _run(engine: WorkflowEngine, yaml: str) -> ProcessInstance:
    definition = load_definition_from_yaml(yaml)
    process = await engine.create_process(definition)
    await engine.start_process(process.id)
    return await engine.store.load_process(process.id)


async def _assert_children_never_queued(engine: WorkflowEngine, parent: ProcessInstance) -> None:
    store: _QueueWatchingStore = engine.store
    assert parent.state == ProcessState.COMPLETE
    children = await store.list_child_processes(parent.id)
    assert children, "the parent should have run at least one child"
    events = await store.load_process_events([c.id for c in children])
    for child in children:
        first = store.first_saves[child.id]
        assert first.parent_process_id == parent.id
        assert first.parent_task_id is not None
        assert child.id not in store.queued_ids
        started = [
            e
            for e in events
            if e.process_id == child.id and e.kind == ProcessEventKind.PROCESS_STARTED
        ]
        assert len(started) == 1


async def test_execute_goal_workflow_child_never_queued():
    engine = _engine()
    parent = await _run(
        engine,
        """
name: Goal
first_task_id: execute
tasks:
  execute:
    name: Execute
    action: execute_goal_workflow
    properties:
      workflow_name: Child
      goal: Count from 1 to 100
""",
    )
    await _assert_children_never_queued(engine, parent)


async def test_subworkflow_child_never_queued():
    engine = _engine()
    parent = await _run(
        engine,
        """
name: Parent
first_task_id: spawn
tasks:
  spawn:
    name: Spawn
    action: subworkflow
    properties:
      workflow: {id: child, name: Child, first_task_id: only,
                 tasks: {only: {id: only, name: Only, action: ok}}, routings: []}
""",
    )
    await _assert_children_never_queued(engine, parent)


async def test_parallel_subworkflows_children_never_queued():
    engine = _engine()
    parent = await _run(
        engine,
        """
name: Parent
first_task_id: fan_out
tasks:
  fan_out:
    name: Fan out
    action: parallel_subworkflows
    properties:
      workflows:
        - key: a
          workflow: {id: a, name: A, first_task_id: only,
                     tasks: {only: {id: only, name: Only, action: ok}}, routings: []}
        - key: b
          workflow: {id: b, name: B, first_task_id: only,
                     tasks: {only: {id: only, name: Only, action: ok}}, routings: []}
""",
    )
    await _assert_children_never_queued(engine, parent)
