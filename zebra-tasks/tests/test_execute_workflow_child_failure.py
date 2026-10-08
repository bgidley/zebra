"""execute_goal_workflow reports failure when a child task fails (GitLab #131).

Uses a real engine + InMemoryStore so the child process state is produced by
the engine rather than mocked: a child whose task returns ``TaskResult.fail``
must end FAILED, and the parent action must surface the task's error.
"""

from unittest.mock import MagicMock, patch

from zebra.core.engine import WorkflowEngine
from zebra.core.models import (
    ProcessDefinition,
    ProcessState,
    RoutingDefinition,
    TaskDefinition,
    TaskInstance,
    TaskResult,
    TaskState,
)
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import ExecutionContext, TaskAction
from zebra.tasks.registry import ActionRegistry

from zebra_tasks.agent.execute_workflow import ExecuteGoalWorkflowAction


class _FailAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        return TaskResult.fail("NameError: name 'fire_number' is not defined")


class _OkAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        return TaskResult.ok(output="report")


async def _run_parent_action(**extra_props):
    """Run ExecuteGoalWorkflowAction on a child whose first task fails."""
    store = InMemoryStore()
    registry = ActionRegistry()
    registry.register_defaults()
    registry.register_action("calc_fail", _FailAction)
    registry.register_action("report_ok", _OkAction)
    engine = WorkflowEngine(store, registry)

    child_def = ProcessDefinition(
        id="fire",
        name="FIRE Retirement Calculator",
        first_task_id="calculate_fire",
        tasks={
            "calculate_fire": TaskDefinition(
                id="calculate_fire", name="Calculate", action="calc_fail"
            ),
            "generate_report": TaskDefinition(
                id="generate_report", name="Report", action="report_ok"
            ),
        },
        routings=[
            RoutingDefinition(
                id="r1", source_task_id="calculate_fire", dest_task_id="generate_report"
            )
        ],
    )
    library = MagicMock()
    library.get_workflow.return_value = child_def

    parent_def = ProcessDefinition(
        id="parent",
        name="Parent",
        first_task_id="execute",
        tasks={"execute": TaskDefinition(id="execute", name="Execute", auto=False)},
        routings=[],
    )
    parent = await engine.create_process(parent_def)
    await engine.start_process(parent.id)
    (parent_task,) = await engine.get_pending_tasks(parent.id)
    parent_task.properties.update(
        {
            "workflow_name": "FIRE Retirement Calculator",
            "goal": "Retire?",
            "timeout": 5,
            **extra_props,
        }
    )
    parent = await store.load_process(parent.id)

    context = ExecutionContext(
        engine=engine,
        store=store,
        process=parent,
        process_definition=parent_def,
        task_definition=parent_def.tasks["execute"],
        extras={"__workflow_library__": library},
    )

    result = await ExecuteGoalWorkflowAction().run(parent_task, context)
    return result, store, parent


async def test_child_task_failure_fails_parent_action():
    result, store, parent = await _run_parent_action()

    assert result.success is False
    assert "fire_number" in result.error

    (child,) = await store.get_processes_by_state(ProcessState.FAILED)
    assert child.parent_process_id == parent.id
    assert child.properties["__failed_task__"] == "calculate_fire"
    assert await store.get_processes_by_state(ProcessState.COMPLETE) == []
    tasks = await store.load_tasks_for_process(child.id)
    assert {t.task_definition_id: t.state for t in tasks} == {"calculate_fire": TaskState.FAILED}


async def test_continue_on_failure_records_child_failure_as_output():
    """#140: with continue_on_failure the task completes and carries the failure as data."""
    result, store, parent = await _run_parent_action(continue_on_failure=True)

    assert result.success is True
    assert result.output["success"] is False
    assert "fire_number" in result.output["error"]
    (child,) = await store.get_processes_by_state(ProcessState.FAILED)
    assert child.parent_process_id == parent.id


async def test_continue_on_failure_records_execution_exception_as_output():
    """#140: an exception while running the child is also carried as data."""
    with patch.object(
        ExecuteGoalWorkflowAction, "_spawn_child", side_effect=RuntimeError("store down")
    ):
        result, _, parent = await _run_parent_action(continue_on_failure=True)

    assert result.success is True
    assert result.output["success"] is False
    assert "store down" in result.output["error"]
