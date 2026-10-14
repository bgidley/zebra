"""execute_goal_workflow timeouts (GitLab #142, #185).

The child's auto tasks run inline inside start_process, so before #142 the
``timeout`` property only applied after the child had already finished. The task
then suspends on the child (#185), so time a human spends answering the child's
form is never counted against the goal. Uses a real engine + InMemoryStore.
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
    action = ExecuteGoalWorkflowAction()
    suspended = await action.run(parent_task, context)
    assert loop.time() - began < 5

    # Resume as the engine would once the (already failed) child is terminal.
    context.subflow_results = [{"process_id": pid} for pid in suspended.suspend_children]
    result = await action.run(parent_task, context)

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
        context.set_process_property("answer", "geared up")
        return TaskResult.ok(output="spent")


HUMAN_CHILD = ProcessDefinition(
    id="gear-child",
    name="Gear Child",
    first_task_id="ask",
    properties={"result_key": "answer"},
    tasks={
        "ask": TaskDefinition(id="ask", name="Ask", action="spend"),
        "form": TaskDefinition(id="form", name="Form", auto=False),
        "after": TaskDefinition(id="after", name="After"),
    },
    routings=[
        RoutingDefinition(id="r1", source_task_id="ask", dest_task_id="form"),
        RoutingDefinition(id="r2", source_task_id="form", dest_task_id="after"),
    ],
)

GOAL_DEF = ProcessDefinition(
    id="goal",
    name="Goal",
    first_task_id="execute",
    tasks={
        "execute": TaskDefinition(
            id="execute",
            name="Execute Goal Workflow",
            action="execute_goal_workflow",
            properties={
                "workflow_name": "Gear Child",
                "goal": "Go",
                "timeout": 5,
                "continue_on_failure": True,
            },
        ),
        "record": TaskDefinition(id="record", name="Record"),
    },
    routings=[RoutingDefinition(id="g1", source_task_id="execute", dest_task_id="record")],
)


class _LlmTimeoutAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        return TaskResult.fail("Request timed out.")


FAILING_AFTER_FORM = HUMAN_CHILD.model_copy(
    update={
        "tasks": {
            **HUMAN_CHILD.tasks,
            "after": TaskDefinition(id="after", name="After", action="llm_timeout"),
        }
    }
)


def _goal_engine(
    child_def: ProcessDefinition = HUMAN_CHILD,
) -> tuple[WorkflowEngine, InMemoryStore]:
    store = InMemoryStore()
    registry = ActionRegistry()
    registry.register_defaults()
    registry.register_action("spend", _SpendAction)
    registry.register_action("llm_timeout", _LlmTimeoutAction)
    registry.register_action("execute_goal_workflow", ExecuteGoalWorkflowAction)
    library = MagicMock()
    library.get_workflow.return_value = child_def
    return WorkflowEngine(store, registry, extras={"__workflow_library__": library}), store


async def _parked_goal(engine: WorkflowEngine, store: InMemoryStore, goal_timeout: float):
    """Run a goal under its goal timeout until its child parks on the human form."""
    goal = await engine.create_process(GOAL_DEF)
    loop = asyncio.get_running_loop()
    began = loop.time()
    await engine.start_process_with_timeout(goal.id, goal_timeout)
    assert loop.time() - began < goal_timeout  # returned on the park, not the deadline

    (child,) = [p for p in await store.list_processes() if p.parent_process_id == goal.id]
    (form,) = await engine.get_pending_tasks(child.id)
    return goal, child, form


async def test_goal_waiting_on_childs_human_task_is_not_timed_out():
    """#185: the goal timeout must not fail a goal whose child waits on a human.

    The goal's run returns once the child parks, so the human can answer long after
    the goal timeout; the goal then resumes and records the child's result and cost.
    """
    engine, store = _goal_engine()
    goal, child, form = await _parked_goal(engine, store, goal_timeout=0.3)

    (execute,) = await store.load_tasks_for_process(goal.id)
    assert execute.state == TaskState.AWAITING_SUBFLOW
    await asyncio.sleep(0.5)  # well past the goal timeout
    assert (await store.load_process(goal.id)).state == ProcessState.RUNNING

    await engine.complete_task(form.id, TaskResult.ok(output={"size": "M"}))

    goal = await store.load_process(goal.id)
    assert goal.state == ProcessState.COMPLETE
    outcome = goal.properties["execution_result"]
    assert outcome["success"] is True
    assert outcome["output"] == "geared up"
    assert outcome["cost"] == 0.2
    assert outcome["tokens_used"] == 300
    assert (outcome["input_tokens"], outcome["output_tokens"]) == (100, 200)
    assert outcome["user_inputs"] == {"Form": {"size": "M"}}


async def test_child_failing_after_human_task_resumes_goal_with_error_and_cost():
    """#183/#185: a child that fails after the submit (e.g. an LLM call timing out) is
    collected by the resumed goal with its error and what it had already spent."""
    engine, store = _goal_engine(FAILING_AFTER_FORM)
    goal, child, form = await _parked_goal(engine, store, goal_timeout=5)

    await engine.complete_task(form.id, TaskResult.ok(output={}))

    assert (await store.load_process(child.id)).state == ProcessState.FAILED
    goal = await store.load_process(goal.id)
    assert goal.state == ProcessState.COMPLETE  # continue_on_failure: recorded as data
    outcome = goal.properties["execution_result"]
    assert outcome["success"] is False
    assert "Request timed out." in outcome["error"]
    assert outcome["cost"] == 0.2
    assert (outcome["input_tokens"], outcome["output_tokens"]) == (100, 200)


async def test_failing_a_goal_fails_its_waiting_child():
    """#185: a failed goal (timeout, kill switch, cancel) leaves no orphaned human task."""
    engine, store = _goal_engine()
    goal, child, _ = await _parked_goal(engine, store, goal_timeout=5)

    await engine.fail_process(goal.id, "Kill switch activated")

    child = await store.load_process(child.id)
    assert child.state == ProcessState.FAILED
    assert await engine.get_pending_tasks(child.id) == []
