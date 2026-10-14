"""F129: ExecuteGoalWorkflowAction is resumable after an interruption.

A goal's ``execute_workflow`` task spawns a child workflow process and suspends on
it (#185). If the task is interrupted while running (e.g. a redeploy kills the web
thread), re-running it must re-attach to that child rather than spawn a duplicate,
and crash recovery (``resume_all_processes``) must re-drive the goal to completion.
"""

import asyncio

import pytest
from zebra.core.engine import PENDING_SUBFLOWS_KEY, WorkflowEngine
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

from zebra_tasks.agent.execute_workflow import CHILD_PROCESS_ID_KEY, ExecuteGoalWorkflowAction

CHILD_DEF = ProcessDefinition(
    id="child_wf",
    name="Child",
    first_task_id="ask",
    properties={"result_key": "answer"},
    tasks={
        # Human task keeps the child RUNNING until the test completes it.
        "ask": TaskDefinition(id="ask", name="Ask", auto=False),
        "answer": TaskDefinition(id="answer", name="Answer", action="answer"),
    },
    routings=[RoutingDefinition(id="r1", source_task_id="ask", dest_task_id="answer")],
)

PARENT_DEF = ProcessDefinition(
    id="parent_wf",
    name="Parent",
    first_task_id="execute_workflow",
    tasks={
        "execute_workflow": TaskDefinition(
            id="execute_workflow",
            name="Execute Goal Workflow",
            action="execute_goal_workflow",
            properties={
                "idempotent": True,
                "workflow_name": "Child",
                "goal": "What is the answer?",
                "timeout": 5,
            },
        ),
    },
)


class AnswerAction(TaskAction):
    calls = 0

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        AnswerAction.calls += 1
        context.set_process_property("answer", "42")
        return TaskResult.ok(output="42")


class _Library:
    def get_workflow(self, name: str) -> ProcessDefinition:
        assert name == "Child"
        return CHILD_DEF


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture
def engine(store):
    AnswerAction.calls = 0
    registry = ActionRegistry()
    registry.register_action("execute_goal_workflow", ExecuteGoalWorkflowAction)
    registry.register_action("answer", AnswerAction)
    return WorkflowEngine(store, registry, extras={"__workflow_library__": _Library()})


async def _children(store: InMemoryStore) -> list:
    processes = await store.list_processes(include_completed=True)
    return [p for p in processes if p.definition_id == CHILD_DEF.id]


async def _human_task(engine: WorkflowEngine, child_id: str) -> TaskInstance:
    pending = await engine.get_pending_tasks(child_id)
    return next(t for t in pending if t.task_definition_id == "ask")


async def _interrupt(store: InMemoryStore, task_id: str) -> TaskInstance:
    """Leave the task RUNNING with its child recorded, as a killed driver would.

    Before #185 the task polled its child while RUNNING, so a redeploy left it in
    exactly this state; prod goals in flight at deploy time are still like this.
    """
    task = await store.load_task(task_id)
    props = {k: v for k, v in task.properties.items() if k != PENDING_SUBFLOWS_KEY}
    task = task.model_copy(update={"state": TaskState.RUNNING, "properties": props})
    await store.save_task(task)
    return task


async def _interrupted_goal(engine: WorkflowEngine, store: InMemoryStore):
    """Start a goal whose child parks on a human task, then interrupt its task."""
    parent = await engine.create_process(PARENT_DEF)
    await engine.start_process(parent.id)

    (child,) = await _children(store)
    assert await engine.get_pending_tasks(child.id)
    (task,) = await store.load_tasks_for_process(parent.id)
    assert task.state == TaskState.AWAITING_SUBFLOW
    assert task.properties[CHILD_PROCESS_ID_KEY] == child.id
    return parent, child, await _interrupt(store, task.id)


def _context(engine, store, parent) -> ExecutionContext:
    return ExecutionContext(
        engine=engine,
        store=store,
        process=parent,
        process_definition=PARENT_DEF,
        task_definition=PARENT_DEF.tasks["execute_workflow"],
        extras=engine.extras,
    )


async def test_parked_child_suspends_the_task(engine, store):
    """#185: the goal's run returns while the child waits on a human."""
    parent, child, _ = await _interrupted_goal(engine, store)
    assert (await store.load_process(parent.id)).state == ProcessState.RUNNING
    assert AnswerAction.calls == 0


async def test_rerun_reattaches_to_running_child(engine, store):
    parent, child, task = await _interrupted_goal(engine, store)

    result = await ExecuteGoalWorkflowAction().run(task, _context(engine, store, parent))

    assert result.suspend_children == [child.id]  # waits on the same child
    assert len(await _children(store)) == 1  # no duplicate child


async def test_rerun_collects_already_completed_child(engine, store):
    parent, child, task = await _interrupted_goal(engine, store)
    # The child finished on its own while nobody was attached.
    await engine.complete_task((await _human_task(engine, child.id)).id, TaskResult.ok())
    assert (await store.load_process(child.id)).state == ProcessState.COMPLETE

    action = ExecuteGoalWorkflowAction()
    context = _context(engine, store, parent)
    result = await action.run(task, context)
    assert result.suspend_children == [child.id]
    context.subflow_results = [{"process_id": child.id}]
    result = await action.run(task, context)

    assert result.success is True
    assert result.output["output"] == "42"
    assert len(await _children(store)) == 1
    assert AnswerAction.calls == 1


async def test_rerun_spawns_new_child_when_recorded_child_is_not_linked(engine, store):
    parent, child, task = await _interrupted_goal(engine, store)
    stranger = await engine.create_process(CHILD_DEF)  # not linked to this task
    task.properties[CHILD_PROCESS_ID_KEY] = stranger.id

    result = await ExecuteGoalWorkflowAction().run(task, _context(engine, store, parent))

    (new_child_id,) = result.suspend_children
    assert new_child_id not in (stranger.id, child.id)
    assert task.properties[CHILD_PROCESS_ID_KEY] == new_child_id
    new_child = await store.load_process(new_child_id)
    assert new_child.parent_process_id == parent.id
    assert new_child.parent_task_id == task.id
    assert await engine.get_pending_tasks(new_child_id)


async def test_recovery_resumes_interrupted_goal_without_duplicate_child(engine, store):
    parent, child, task = await _interrupted_goal(engine, store)

    # Recovery re-runs execute_workflow (idempotent): it re-attaches and suspends.
    resumed = await asyncio.wait_for(engine.resume_all_processes(), timeout=3)
    assert {p.id for p in resumed} == {parent.id, child.id}
    assert (await store.load_task(task.id)).state == TaskState.AWAITING_SUBFLOW

    await engine.complete_task((await _human_task(engine, child.id)).id, TaskResult.ok())

    parent = await store.load_process(parent.id)
    assert parent.state == ProcessState.COMPLETE
    assert parent.properties["execution_result"]["output"] == "42"
    assert len(await _children(store)) == 1
    assert AnswerAction.calls == 1


async def test_suspended_goal_survives_restarts(engine, store):
    """#185: a goal waiting on a human is not RUNNING, so restarts don't count against it."""
    parent = await engine.create_process(PARENT_DEF)
    await engine.start_process(parent.id)
    (task,) = await store.load_tasks_for_process(parent.id)

    for _ in range(4):
        await asyncio.wait_for(engine.resume_all_processes(max_interrupted_attempts=3), timeout=3)

    assert (await store.load_process(parent.id)).state == ProcessState.RUNNING
    reloaded = await store.load_task(task.id)
    assert reloaded.state == TaskState.AWAITING_SUBFLOW
    assert reloaded.execution_attempt == 0
    assert len(await _children(store)) == 1


async def test_goal_interrupted_three_times_auto_fails(engine, store):
    """#129 + #130: execute_workflow is idempotent, so recovery re-runs it — but each
    interruption still counts toward the recovery cap, and the 3rd fails the goal."""
    parent, child, task = await _interrupted_goal(engine, store)

    # Interruptions 1 and 2: recovery re-attaches to the child, then is interrupted again.
    for attempt in (1, 2):
        await asyncio.wait_for(engine.resume_all_processes(max_interrupted_attempts=3), timeout=3)
        reloaded = await store.load_task(task.id)
        assert reloaded.state == TaskState.AWAITING_SUBFLOW
        assert reloaded.execution_attempt == attempt
        await _interrupt(store, task.id)

    # Interruption 3 hits the cap: the goal fails instead of being re-run again.
    resumed = await asyncio.wait_for(
        engine.resume_all_processes(max_interrupted_attempts=3), timeout=3
    )

    assert parent.id not in {p.id for p in resumed}
    failed = await store.load_process(parent.id)
    assert failed.state == ProcessState.FAILED
    assert "Execute Goal Workflow" in failed.properties["__error__"]
    assert "interrupted 3 times" in failed.properties["__error__"]
    assert len(await _children(store)) == 1  # never spawned a duplicate child
    # #185: the child is failed with the goal, not left waiting on its human task.
    child = await store.load_process(child.id)
    assert child.state == ProcessState.FAILED
    assert await engine.get_pending_tasks(child.id) == []
    assert AnswerAction.calls == 0
