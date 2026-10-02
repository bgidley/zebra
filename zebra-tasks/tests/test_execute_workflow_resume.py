"""F129: ExecuteGoalWorkflowAction is resumable after an interruption.

A goal's ``execute_workflow`` task spawns a child workflow process. If the
process driving it dies (e.g. a redeploy kills the web thread), re-running the
task must re-attach to that child rather than spawn a duplicate, and crash
recovery (``resume_all_processes``) must re-drive the goal to completion.
"""

import asyncio

import pytest
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


async def _wait_for(predicate, timeout: float = 3.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    while not await predicate():
        assert asyncio.get_event_loop().time() < deadline, "condition not met in time"
        await asyncio.sleep(0.02)


async def _human_task(engine: WorkflowEngine, child_id: str) -> TaskInstance:
    pending = await engine.get_pending_tasks(child_id)
    return next(t for t in pending if t.task_definition_id == "ask")


async def _interrupted_goal(engine: WorkflowEngine, store: InMemoryStore):
    """Start a goal, wait until its child is spawned, then kill the driver.

    Mirrors a redeploy killing the web thread: the parent process and its
    ``execute_workflow`` task are left RUNNING; the child keeps its own state.
    """
    parent = await engine.create_process(PARENT_DEF)
    driver = asyncio.create_task(engine.start_process(parent.id))

    async def child_waiting() -> bool:
        children = await _children(store)
        return bool(children) and bool(await engine.get_pending_tasks(children[0].id))

    await _wait_for(child_waiting)
    driver.cancel()
    with pytest.raises(asyncio.CancelledError):
        await driver

    (child,) = await _children(store)
    (task,) = await store.load_tasks_for_process(parent.id)
    assert task.state == TaskState.RUNNING
    assert task.properties[CHILD_PROCESS_ID_KEY] == child.id
    return parent, child, task


def _context(engine, store, parent) -> ExecutionContext:
    return ExecutionContext(
        engine=engine,
        store=store,
        process=parent,
        process_definition=PARENT_DEF,
        task_definition=PARENT_DEF.tasks["execute_workflow"],
        extras=engine.extras,
    )


async def test_rerun_reattaches_to_running_child(engine, store):
    parent, child, task = await _interrupted_goal(engine, store)

    rerun = asyncio.create_task(
        ExecuteGoalWorkflowAction().run(task, _context(engine, store, parent))
    )
    await asyncio.sleep(0.1)
    assert not rerun.done()  # waiting on the still-running child

    await engine.complete_task((await _human_task(engine, child.id)).id, TaskResult.ok())
    result = await asyncio.wait_for(rerun, timeout=3)

    assert result.success is True
    assert result.output["output"] == "42"
    assert len(await _children(store)) == 1  # no duplicate child
    assert AnswerAction.calls == 1


async def test_rerun_collects_already_completed_child(engine, store):
    parent, child, task = await _interrupted_goal(engine, store)
    # The child finished on its own while nobody was attached.
    await engine.complete_task((await _human_task(engine, child.id)).id, TaskResult.ok())
    assert (await store.load_process(child.id)).state == ProcessState.COMPLETE

    result = await asyncio.wait_for(
        ExecuteGoalWorkflowAction().run(task, _context(engine, store, parent)), timeout=3
    )

    assert result.success is True
    assert result.output["output"] == "42"
    assert len(await _children(store)) == 1
    assert AnswerAction.calls == 1


async def test_rerun_spawns_new_child_when_recorded_child_is_not_linked(engine, store):
    parent, child, task = await _interrupted_goal(engine, store)
    stranger = await engine.create_process(CHILD_DEF)  # not linked to this task
    task.properties[CHILD_PROCESS_ID_KEY] = stranger.id

    rerun = asyncio.create_task(
        ExecuteGoalWorkflowAction().run(task, _context(engine, store, parent))
    )

    async def new_child_waiting() -> bool:
        new_id = task.properties[CHILD_PROCESS_ID_KEY]
        return new_id not in (stranger.id, child.id) and bool(
            await engine.get_pending_tasks(new_id)
        )

    await _wait_for(new_child_waiting)
    new_child_id = task.properties[CHILD_PROCESS_ID_KEY]
    await engine.complete_task((await _human_task(engine, new_child_id)).id, TaskResult.ok())
    result = await asyncio.wait_for(rerun, timeout=3)

    assert result.success is True
    new_child = await store.load_process(new_child_id)
    assert new_child.parent_process_id == parent.id
    assert new_child.parent_task_id == task.id


async def test_recovery_resumes_interrupted_goal_without_duplicate_child(engine, store):
    parent, child, _ = await _interrupted_goal(engine, store)

    recovery = asyncio.create_task(engine.resume_all_processes())
    await asyncio.sleep(0.1)
    # Recovery re-ran execute_workflow (idempotent) — it is waiting on the same child.
    assert not recovery.done()
    await engine.complete_task((await _human_task(engine, child.id)).id, TaskResult.ok())
    resumed = await asyncio.wait_for(recovery, timeout=3)

    assert {p.id for p in resumed} == {parent.id, child.id}
    parent = await store.load_process(parent.id)
    assert parent.state == ProcessState.COMPLETE
    assert parent.properties["execution_result"]["output"] == "42"
    assert len(await _children(store)) == 1
    assert AnswerAction.calls == 1


async def test_goal_interrupted_three_times_auto_fails(engine, store):
    """#129 + #130: execute_workflow is idempotent, so recovery re-runs it — but each
    interruption still counts toward the recovery cap, and the 3rd fails the goal."""
    parent, child, task = await _interrupted_goal(engine, store)

    # Interruptions 1 and 2: recovery re-attaches to the child, then is killed again.
    for attempt in (1, 2):
        recovery = asyncio.create_task(engine.resume_all_processes(max_interrupted_attempts=3))
        await asyncio.sleep(0.1)
        assert not recovery.done()  # re-attached and waiting on the child
        recovery.cancel()
        with pytest.raises(asyncio.CancelledError):
            await recovery
        reloaded = await store.load_task(task.id)
        assert reloaded.state == TaskState.RUNNING
        assert reloaded.execution_attempt == attempt

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
    assert AnswerAction.calls == 0
