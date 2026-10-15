"""#187: retrying a failed run resumes where it stopped instead of re-asking.

A continuation the assessor marks ``same_workflow`` of a run that failed in that
workflow starts the new goal-workflow process at the task(s) the failed one never
completed, carrying its answers and outputs over. Uses a real engine + InMemoryStore.
"""

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import (
    ProcessDefinition,
    ProcessState,
    RoutingDefinition,
    TaskDefinition,
    TaskInstance,
    TaskResult,
)
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import ExecutionContext, TaskAction
from zebra.tasks.registry import ActionRegistry

from zebra_tasks.agent.execute_workflow import RESUMED_FROM_KEY, ExecuteGoalWorkflowAction

CHILD_DEF = ProcessDefinition(
    id="gear_wf",
    name="Gear",
    first_task_id="ask",
    properties={"result_key": "brief"},
    tasks={
        "ask": TaskDefinition(id="ask", name="Ask", auto=False),
        "profile": TaskDefinition(id="profile", name="Profile", action="profile"),
        "handoff": TaskDefinition(id="handoff", name="Handoff", action="handoff"),
    },
    routings=[
        RoutingDefinition(id="r1", source_task_id="ask", dest_task_id="profile"),
        RoutingDefinition(id="r2", source_task_id="profile", dest_task_id="handoff"),
    ],
)

PARENT_DEF = ProcessDefinition(
    id="loop_wf",
    name="Loop",
    first_task_id="execute_workflow",
    tasks={
        "execute_workflow": TaskDefinition(
            id="execute_workflow",
            name="Execute Goal Workflow",
            action="execute_goal_workflow",
            properties={
                "workflow_name": "Gear",
                "goal": "{{goal}}",
                "timeout": 5,
                "continue_on_failure": True,
            },
        ),
    },
)


class ProfileAction(TaskAction):
    calls = 0

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        ProfileAction.calls += 1
        answer = context.get_process_property("__task_output_ask")
        context.set_process_property("profile", f"profile of {answer['discipline']}")
        return TaskResult.ok(output="profiled")


class HandoffAction(TaskAction):
    fail = True

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        if HandoffAction.fail:
            return TaskResult.fail("Timed out")
        profile = context.get_process_property("profile")
        context.set_process_property("brief", f"brief from {profile}")
        return TaskResult.ok(output="briefed")


class _Library:
    definition = CHILD_DEF

    def get_workflow(self, name: str) -> ProcessDefinition:
        assert name == self.definition.name
        return self.definition


@pytest.fixture
def library():
    return _Library()


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture
def engine(store, library):
    ProfileAction.calls = 0
    HandoffAction.fail = True
    registry = ActionRegistry()
    registry.register_action("execute_goal_workflow", ExecuteGoalWorkflowAction)
    registry.register_action("profile", ProfileAction)
    registry.register_action("handoff", HandoffAction)
    return WorkflowEngine(store, registry, extras={"__workflow_library__": library})


async def _children(store, parent_id):
    return await store.list_child_processes(parent_id)


async def _failed_run(engine, store):
    """Run 1: the user answers the form, then the last step fails."""
    root = await engine.create_process(PARENT_DEF, {"goal": "Buy kayak kit", "run_id": "run-1"})
    await engine.start_process(root.id)
    (child,) = await _children(store, root.id)
    (ask,) = await engine.get_pending_tasks(child.id)
    await engine.complete_task(ask.id, TaskResult.ok(output={"discipline": "whitewater"}))
    child = await store.load_process(child.id)
    assert child.state == ProcessState.FAILED
    return child


async def _retry(
    engine,
    store,
    decision="same_workflow",
    success=False,
    run_id="run-2",
    previous_run_id="run-1",
    handoff_fails=False,
):
    """Run 2: the user continues run 1 with the comment "Retry"."""
    HandoffAction.fail = handoff_fails
    root = await engine.create_process(
        PARENT_DEF,
        {
            "goal": "Buy kayak kit",
            "run_id": run_id,
            "continuation_comment": "Retry",
            "continuation_decision": decision,
            "previous_run_context": {
                "run_id": previous_run_id,
                "workflow_name": "Gear",
                "success": success,
            },
        },
    )
    await engine.start_process(root.id)
    (child,) = await _children(store, root.id)
    return await store.load_process(root.id), await store.load_process(child.id)


async def test_retry_resumes_at_failed_task_without_reasking(engine, store):
    previous = await _failed_run(engine, store)

    root, child = await _retry(engine, store)

    assert await engine.get_pending_tasks(child.id) == []  # nothing asked again
    assert child.state == ProcessState.COMPLETE
    assert child.properties["__task_output_ask"] == {"discipline": "whitewater"}
    assert child.properties["brief"] == "brief from profile of whitewater"
    assert child.properties[RESUMED_FROM_KEY] == {
        "process_id": previous.id,
        "task_ids": ["handoff"],
    }
    assert ProfileAction.calls == 1  # completed steps are not re-run
    assert root.properties["execution_result"]["success"] is True
    assert root.properties["execution_result"]["output"] == "brief from profile of whitewater"


async def test_resumed_child_starts_its_own_bookkeeping(engine, store):
    previous = await _failed_run(engine, store)
    assert "__error__" in previous.properties

    _, child = await _retry(engine, store)

    assert "__error__" not in child.properties
    assert child.properties["__parent_process_id__"] != previous.properties["__parent_process_id__"]


@pytest.mark.parametrize(
    ("decision", "success"),
    [("existing_workflow", False), ("same_workflow", True)],
)
async def test_other_continuations_start_from_the_beginning(engine, store, decision, success):
    await _failed_run(engine, store)

    _, child = await _retry(engine, store, decision=decision, success=success)

    (pending,) = await engine.get_pending_tasks(child.id)
    assert pending.task_definition_id == "ask"
    assert RESUMED_FROM_KEY not in child.properties


async def test_changed_workflow_starts_from_the_beginning(engine, store, library):
    await _failed_run(engine, store)
    library.definition = CHILD_DEF.model_copy(
        update={
            "id": "gear_wf_v2",
            "tasks": {k: v for k, v in CHILD_DEF.tasks.items() if k != "handoff"},
            "routings": CHILD_DEF.routings[:1],
        }
    )

    _, child = await _retry(engine, store)

    (pending,) = await engine.get_pending_tasks(child.id)
    assert pending.task_definition_id == "ask"


async def test_unfinished_join_starts_from_the_beginning(engine, store, library):
    await _failed_run(engine, store)
    handoff = CHILD_DEF.tasks["handoff"].model_copy(update={"synchronized": True})
    tasks = {**CHILD_DEF.tasks, "handoff": handoff}
    library.definition = CHILD_DEF.model_copy(update={"tasks": tasks})

    _, child = await _retry(engine, store)

    (pending,) = await engine.get_pending_tasks(child.id)
    assert pending.task_definition_id == "ask"


async def test_retry_of_a_retry_resumes_from_the_latest_attempt(engine, store):
    await _failed_run(engine, store)
    _, first_retry = await _retry(engine, store, handoff_fails=True)
    assert first_retry.state == ProcessState.FAILED

    _, child = await _retry(engine, store, run_id="run-3", previous_run_id="run-2")

    assert child.state == ProcessState.COMPLETE
    assert child.properties[RESUMED_FROM_KEY]["process_id"] == first_retry.id
    assert child.properties["__task_output_ask"] == {"discipline": "whitewater"}
    assert ProfileAction.calls == 1


async def test_unknown_previous_run_starts_from_the_beginning(engine, store):
    _, child = await _retry(engine, store)

    (pending,) = await engine.get_pending_tasks(child.id)
    assert pending.task_definition_id == "ask"
