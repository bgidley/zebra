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


class _SpendAction(TaskAction):
    """Records LLM spend on the process, as llm_call does."""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        context.set_process_property("__total_cost__", 0.2)
        context.set_process_property("__total_tokens__", 300)
        context.set_process_property(
            "__token_history__", [{"input": 100, "output": 200, "total": 300, "cost": 0.2}]
        )
        return TaskResult.ok(output="spent")


class _HungAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        await asyncio.sleep(0.6)
        return TaskResult.ok(output="too late")


async def test_hang_after_human_task_fails_child_and_reports_cost():
    """#183: a hung auto task after a human form fails the child and keeps its cost.

    The human submit (``complete_task``) drives the rest of the chain inline, outside
    ``start_process_with_timeout``, so only the parent's wait loop can bound it.
    """
    store = InMemoryStore()
    registry = ActionRegistry()
    registry.register_defaults()
    registry.register_action("spend", _SpendAction)
    registry.register_action("hung", _HungAction)
    engine = WorkflowEngine(store, registry)

    child_def = ProcessDefinition(
        id="gear-child",
        name="Gear Child",
        first_task_id="ask",
        tasks={
            "ask": TaskDefinition(id="ask", name="Ask", action="spend"),
            "form": TaskDefinition(id="form", name="Form", auto=False),
            "handoff": TaskDefinition(id="handoff", name="Handoff", action="hung"),
            "after": TaskDefinition(id="after", name="After"),
        },
        routings=[
            RoutingDefinition(id="r1", source_task_id="ask", dest_task_id="form"),
            RoutingDefinition(id="r2", source_task_id="form", dest_task_id="handoff"),
            RoutingDefinition(id="r3", source_task_id="handoff", dest_task_id="after"),
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
    parent_task.properties.update({"workflow_name": "Gear Child", "goal": "Go", "timeout": "0.2"})
    parent = await store.load_process(parent.id)
    context = ExecutionContext(
        engine=engine,
        store=store,
        process=parent,
        process_definition=parent_def,
        task_definition=parent_def.tasks["execute"],
        extras={"__workflow_library__": library},
    )

    run = asyncio.create_task(ExecuteGoalWorkflowAction().run(parent_task, context))

    # Wait for the child to park on its form, then submit it the way the web UI does.
    form_task = None
    while form_task is None:
        await asyncio.sleep(0.05)
        running = await store.get_processes_by_state(ProcessState.RUNNING)
        child = next((p for p in running if p.parent_process_id == parent.id), None)
        if child is not None:
            pending = await engine.get_pending_tasks(child.id)
            form_task = next((t for t in pending if t.task_definition_id == "form"), None)
    await asyncio.sleep(0.4)  # parked time must not count toward the timeout
    submit = asyncio.create_task(engine.complete_task(form_task.id, TaskResult.ok(output={})))

    result = await run
    assert result.success is False
    assert result.error == "Timeout after 0.2s"
    outcome = parent.properties["execution_result"]
    assert outcome["cost"] == 0.2
    assert outcome["tokens_used"] == 300
    assert (outcome["input_tokens"], outcome["output_tokens"]) == (100, 200)

    child = await store.load_process(child.id)
    assert child.state == ProcessState.FAILED
    assert child.properties["__error__"] == "Timeout after 0.2s"

    # The hung action eventually returns: its result must not revive the child.
    await submit
    child = await store.load_process(child.id)
    assert child.state == ProcessState.FAILED
    assert "__task_output_handoff" not in child.properties
    tasks = await store.load_tasks_for_process(child.id)
    assert {t.task_definition_id: t.state for t in tasks} == {"handoff": TaskState.FAILED}
