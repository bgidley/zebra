"""execute_goal_workflow enforces its timeout on the child's inline run (GitLab #142).

The child's auto tasks run inline inside start_process, so before #142 the
``timeout`` property only applied after the child had already finished. Uses a
real engine + InMemoryStore with a slow child action to prove the child is failed
at the deadline and the parent action reports the timeout.
"""

import asyncio
from unittest.mock import MagicMock

from zebra.core.engine import WorkflowEngine
from zebra.core.models import (
    ProcessDefinition,
    ProcessState,
    TaskDefinition,
    TaskInstance,
    TaskResult,
    TaskState,
)
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import ExecutionContext, TaskAction
from zebra.tasks.registry import ActionRegistry

from zebra_tasks.agent.execute_workflow import ExecuteGoalWorkflowAction


class _SlowAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        await asyncio.sleep(30)
        return TaskResult.ok(output="too late")


async def test_slow_child_is_failed_at_action_timeout():
    store = InMemoryStore()
    registry = ActionRegistry()
    registry.register_defaults()
    registry.register_action("slow", _SlowAction)
    engine = WorkflowEngine(store, registry)

    child_def = ProcessDefinition(
        id="slow-child",
        name="Slow Child",
        first_task_id="work",
        tasks={"work": TaskDefinition(id="work", name="Work", action="slow")},
        routings=[],
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
    parent_task.properties.update({"workflow_name": "Slow Child", "goal": "Go", "timeout": "0.2"})
    parent = await store.load_process(parent.id)

    context = ExecutionContext(
        engine=engine,
        store=store,
        process=parent,
        process_definition=parent_def,
        task_definition=parent_def.tasks["execute"],
        extras={"__workflow_library__": library},
    )

    loop = asyncio.get_running_loop()
    began = loop.time()
    result = await ExecuteGoalWorkflowAction().run(parent_task, context)

    assert loop.time() - began < 5
    assert result.success is False
    assert "Timed out after 0.2s" in result.error

    (child,) = await store.get_processes_by_state(ProcessState.FAILED)
    assert child.parent_process_id == parent.id
    tasks = await store.load_tasks_for_process(child.id)
    assert {t.task_definition_id: t.state for t in tasks} == {"work": TaskState.FAILED}
