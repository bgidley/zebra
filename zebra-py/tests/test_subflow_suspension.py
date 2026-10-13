"""Engine: a task suspends on child processes and resumes when they finish (#146)."""

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

AUTO_CHILD = ProcessDefinition(
    id="auto_child",
    name="Auto Child",
    first_task_id="work",
    properties={"result_key": "answer"},
    tasks={"work": TaskDefinition(id="work", name="Work", action="double")},
)

FAILING_CHILD = ProcessDefinition(
    id="failing_child",
    name="Failing Child",
    first_task_id="work",
    tasks={"work": TaskDefinition(id="work", name="Work", action="boom")},
)

HUMAN_CHILD = ProcessDefinition(
    id="human_child",
    name="Human Child",
    first_task_id="ask",
    properties={"result_key": "answer"},
    tasks={
        "ask": TaskDefinition(id="ask", name="Ask", auto=False),
        "work": TaskDefinition(id="work", name="Work", action="double"),
    },
    routings=[RoutingDefinition(id="r1", source_task_id="ask", dest_task_id="work")],
)

CHILDREN = {d.id: d for d in (AUTO_CHILD, FAILING_CHILD, HUMAN_CHILD)}


def _parent(children: list[str], turns: int = 1) -> ProcessDefinition:
    return ProcessDefinition(
        id=f"parent_{'_'.join(children)}_{turns}",
        name="Parent",
        first_task_id="spawn",
        tasks={
            "spawn": TaskDefinition(
                id="spawn",
                name="Spawn",
                action="spawn",
                properties={"children": children, "turns": turns},
            ),
            "after": TaskDefinition(id="after", name="After", action="record_after"),
        },
        routings=[RoutingDefinition(id="r1", source_task_id="spawn", dest_task_id="after")],
    )


class DoubleAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        answer = context.process.properties.get("n", 0) * 2
        context.set_process_property("answer", answer)
        return TaskResult.ok(output=answer)


class BoomAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        return TaskResult.fail("boom")


class SpawnAction(TaskAction):
    """Suspends on fresh children ``turns`` times, then returns every result seen."""

    calls: list[list[dict] | None] = []

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        SpawnAction.calls.append(context.subflow_results)
        seen = task.properties.setdefault("seen", [])
        if context.subflow_results is not None:
            seen.extend(
                {"output": r["output"], "success": r["success"], "error": r["error"]}
                for r in context.subflow_results
            )
        turn = task.properties.get("turn", 0)
        if turn >= task.properties["turns"]:
            return TaskResult.ok(output=seen)
        task.properties["turn"] = turn + 1
        context.set_process_property("spawned_turns", turn + 1)

        children = []
        for i, def_id in enumerate(task.properties["children"]):
            child = await context.engine.create_process(
                CHILDREN[def_id],
                properties={"n": (turn * 10) + i + 1},
                parent_process_id=context.process.id,
                parent_task_id=task.id,
            )
            children.append(child.id)
        return TaskResult.suspend(children)


class RecordAfterAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        return TaskResult.ok(output="after ran")


@pytest.fixture(autouse=True)
def _reset_calls():
    SpawnAction.calls = []


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture
def registry():
    reg = ActionRegistry()
    reg.register_defaults()
    reg.register_action("double", DoubleAction)
    reg.register_action("boom", BoomAction)
    reg.register_action("spawn", SpawnAction)
    reg.register_action("record_after", RecordAfterAction)
    return reg


@pytest.fixture
def engine(store, registry):
    return WorkflowEngine(store, registry)


async def _run(engine: WorkflowEngine, definition: ProcessDefinition):
    process = await engine.create_process(definition)
    return await engine.start_process(process.id)


async def _children(store: InMemoryStore, parent_id: str):
    return [
        p
        for p in await store.list_processes(include_completed=True)
        if p.parent_process_id == parent_id
    ]


async def _complete_human_task(engine: WorkflowEngine, process_id: str) -> None:
    (task,) = await engine.get_pending_tasks(process_id)
    await engine.complete_task(task.id, TaskResult.ok())


def test_suspend_needs_children():
    with pytest.raises(ValueError):
        TaskResult.suspend([])


async def test_suspend_then_resume_after_child_completes(engine, store):
    process = await _run(engine, _parent(["auto_child"]))

    assert process.state == ProcessState.COMPLETE
    assert process.properties["__task_output_spawn"] == [
        {"output": 2, "success": True, "error": None}
    ]
    assert process.properties["__task_output_after"] == "after ran"
    assert SpawnAction.calls[0] is None
    (result,) = SpawnAction.calls[1]
    assert result["workflow"] == "Auto Child"
    assert result["properties"]["n"] == 1
    (child,) = await _children(store, process.id)
    assert child.state == ProcessState.COMPLETE


async def test_failed_child_is_a_result_not_a_task_failure(engine):
    process = await _run(engine, _parent(["failing_child"]))

    assert process.state == ProcessState.COMPLETE
    (seen,) = process.properties["__task_output_spawn"]
    assert seen["success"] is False
    assert seen["error"] == "boom"


async def test_parallel_children_resume_once_with_ordered_results(engine):
    process = await _run(engine, _parent(["auto_child", "auto_child"]))

    assert process.state == ProcessState.COMPLETE
    assert [s["output"] for s in process.properties["__task_output_spawn"]] == [2, 4]
    assert len(SpawnAction.calls) == 2


async def test_repeated_suspension(engine):
    process = await _run(engine, _parent(["auto_child"], turns=3))

    assert process.state == ProcessState.COMPLETE
    assert [s["output"] for s in process.properties["__task_output_spawn"]] == [2, 22, 42]
    assert len(SpawnAction.calls) == 4
    # Process properties written in a turn that suspended are kept.
    assert process.properties["spawned_turns"] == 3


async def test_human_child_parks_parent_without_polling(engine, store):
    process = await _run(engine, _parent(["human_child"]))

    assert process.state == ProcessState.RUNNING
    (task,) = await store.load_tasks_for_process(process.id)
    assert task.state == TaskState.AWAITING_SUBFLOW
    (child,) = await _children(store, process.id)
    assert task.properties[PENDING_SUBFLOWS_KEY] == [child.id]
    assert child.state == ProcessState.RUNNING

    await _complete_human_task(engine, child.id)

    process = await store.load_process(process.id)
    assert process.state == ProcessState.COMPLETE
    assert process.properties["__task_output_spawn"][0]["output"] == 2


async def test_waits_for_every_child(engine, store):
    process = await _run(engine, _parent(["auto_child", "human_child"]))

    (task,) = await store.load_tasks_for_process(process.id)
    assert task.state == TaskState.AWAITING_SUBFLOW
    assert len(SpawnAction.calls) == 1

    human = next(c for c in await _children(store, process.id) if c.definition_id == "human_child")
    await _complete_human_task(engine, human.id)

    process = await store.load_process(process.id)
    assert process.state == ProcessState.COMPLETE
    assert [s["output"] for s in process.properties["__task_output_spawn"]] == [2, 4]


async def test_failing_the_parent_ignores_a_later_child_completion(engine, store):
    process = await _run(engine, _parent(["human_child"]))
    await engine.fail_process(process.id, "cancelled")
    (child,) = await _children(store, process.id)

    await _complete_human_task(engine, child.id)

    process = await store.load_process(process.id)
    assert process.state == ProcessState.FAILED
    assert len(SpawnAction.calls) == 1


async def test_recovery_resumes_wait_whose_children_finished_while_down(store, registry):
    first = WorkflowEngine(store, registry)
    process = await _run(first, _parent(["human_child"]))
    (child,) = await _children(store, process.id)

    # The child finishes while no engine is running: no hook fires.
    props = {**child.properties, "answer": 99}
    await store.save_process(
        child.model_copy(update={"state": ProcessState.COMPLETE, "properties": props})
    )
    for task in await store.load_tasks_for_process(child.id):
        await store.delete_task(task.id)

    second = WorkflowEngine(store, registry)
    await second.resume_all_processes()

    process = await store.load_process(process.id)
    assert process.state == ProcessState.COMPLETE
    assert process.properties["__task_output_spawn"][0]["output"] == 99


async def test_recovery_starts_a_child_that_never_started(store, registry, monkeypatch):
    first = WorkflowEngine(store, registry)

    async def crash_before_start(task_id: str) -> None:
        return None

    monkeypatch.setattr(first, "_start_subflows", crash_before_start)
    process = await _run(first, _parent(["auto_child"]))
    (child,) = await _children(store, process.id)
    assert child.state == ProcessState.CREATED
    (task,) = await store.load_tasks_for_process(process.id)
    assert task.state == TaskState.AWAITING_SUBFLOW

    second = WorkflowEngine(store, registry)
    await second.resume_all_processes()

    process = await store.load_process(process.id)
    assert process.state == ProcessState.COMPLETE
    assert process.properties["__task_output_spawn"][0]["output"] == 2


async def test_recovery_leaves_running_wait_suspended(store, registry):
    first = WorkflowEngine(store, registry)
    process = await _run(first, _parent(["human_child"]))

    second = WorkflowEngine(store, registry)
    await second.resume_all_processes()

    (task,) = await store.load_tasks_for_process(process.id)
    assert task.state == TaskState.AWAITING_SUBFLOW
    assert task.execution_attempt == 0
    assert MANUAL_REVIEW not in task.properties

    (child,) = await _children(store, process.id)
    await _complete_human_task(second, child.id)
    process = await store.load_process(process.id)
    assert process.state == ProcessState.COMPLETE


MANUAL_REVIEW = "__requires_manual_review__"
