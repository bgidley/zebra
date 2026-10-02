"""Tests that an unhandled task failure fails the owning process (GitLab #131).

A task whose action returns ``TaskResult.fail`` (or raises) is left in the
FAILED state and never routes. Previously the end-of-transition completion
check treated FAILED tasks as "done" and marked the process COMPLETE with no
``__error__`` — hiding the failure from parents such as ``execute_workflow``.
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
    TaskState,
)
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import ExecutionContext, TaskAction
from zebra.tasks.registry import ActionRegistry


class OkAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        return TaskResult.ok(output="ok")


class FailAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        return TaskResult.fail("NameError: name 'x' is not defined")


class RaiseAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        raise RuntimeError("boom")


class RouteAction(TaskAction):
    """Signals a handled failure by routing rather than failing."""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        return TaskResult(success=True, output="handled", next_route="failed")


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture
def engine(store):
    reg = ActionRegistry()
    reg.register_defaults()
    reg.register_action("ok", OkAction)
    reg.register_action("fail", FailAction)
    reg.register_action("raise", RaiseAction)
    reg.register_action("route", RouteAction)
    return WorkflowEngine(store, reg)


def _serial(calc_action: str, *, human_first: bool = False) -> ProcessDefinition:
    """``[ask (human)] -> calc(calc_action) -> report(ok)``."""
    tasks = {
        "calc": TaskDefinition(id="calc", name="Calc", action=calc_action),
        "report": TaskDefinition(id="report", name="Report", action="ok"),
    }
    routings = [RoutingDefinition(id="r2", source_task_id="calc", dest_task_id="report")]
    first = "calc"
    if human_first:
        tasks["ask"] = TaskDefinition(id="ask", name="Ask", auto=False)
        routings.append(RoutingDefinition(id="r1", source_task_id="ask", dest_task_id="calc"))
        first = "ask"
    return ProcessDefinition(
        id=f"serial-{calc_action}-{human_first}",
        name="Serial",
        first_task_id=first,
        tasks=tasks,
        routings=routings,
    )


async def _assert_failed(engine: WorkflowEngine, process_id: str, error: str) -> None:
    process = await engine.store.load_process(process_id)
    assert process.state == ProcessState.FAILED
    assert process.properties["__error__"] == error
    assert process.properties["__failed_task__"] == "calc"
    assert process.completed_at is not None
    tasks = await engine.store.load_tasks_for_process(process_id)
    assert [t.task_definition_id for t in tasks if t.state == TaskState.FAILED] == ["calc"]
    # Downstream task never ran
    assert "__task_output_report" not in process.properties


async def test_auto_task_failure_fails_process(engine):
    process = await engine.create_process(_serial("fail"))
    await engine.start_process(process.id)
    await _assert_failed(engine, process.id, "NameError: name 'x' is not defined")


async def test_auto_task_exception_fails_process(engine):
    process = await engine.create_process(_serial("raise"))
    await engine.start_process(process.id)
    await _assert_failed(engine, process.id, "boom")


async def test_failure_after_human_task_completed_fails_process(engine):
    process = await engine.create_process(_serial("fail", human_first=True))
    await engine.start_process(process.id)
    (ask,) = await engine.get_pending_tasks(process.id)

    await engine.complete_task(ask.id, TaskResult.ok(output={"age": 40}))

    await _assert_failed(engine, process.id, "NameError: name 'x' is not defined")


async def test_failure_after_resume_all_processes_fails_process(engine):
    """Mirror the prod incident: recovery runs while waiting on a human task."""
    process = await engine.create_process(_serial("fail", human_first=True))
    await engine.start_process(process.id)

    resumed = await engine.resume_all_processes()
    assert [p.id for p in resumed] == [process.id]
    reloaded = await engine.store.load_process(process.id)
    assert reloaded.state == ProcessState.RUNNING

    (ask,) = await engine.get_pending_tasks(process.id)
    await engine.complete_task(ask.id, TaskResult.ok(output={"age": 40}))

    await _assert_failed(engine, process.id, "NameError: name 'x' is not defined")


async def test_manual_task_completed_with_failure_fails_process(engine):
    process = await engine.create_process(_serial("ok", human_first=True))
    await engine.start_process(process.id)
    (ask,) = await engine.get_pending_tasks(process.id)

    await engine.complete_task(ask.id, TaskResult.fail("user rejected"))

    process = await engine.store.load_process(process.id)
    assert process.state == ProcessState.FAILED
    assert process.properties["__error__"] == "user rejected"
    assert process.properties["__failed_task__"] == "ask"


async def test_handled_failure_via_routing_still_completes(engine):
    """Explicit failure routing (ok + next_route) keeps COMPLETE semantics."""
    defn = ProcessDefinition(
        id="routed",
        name="Routed",
        first_task_id="check",
        tasks={
            "check": TaskDefinition(id="check", name="Check", action="route"),
            "happy": TaskDefinition(id="happy", name="Happy", action="ok"),
            "recover": TaskDefinition(id="recover", name="Recover", action="ok"),
        },
        routings=[
            RoutingDefinition(
                id="r1",
                source_task_id="check",
                dest_task_id="happy",
                condition="route_name",
                name="success",
            ),
            RoutingDefinition(
                id="r2",
                source_task_id="check",
                dest_task_id="recover",
                condition="route_name",
                name="failed",
            ),
        ],
    )
    process = await engine.create_process(defn)
    await engine.start_process(process.id)

    process = await engine.store.load_process(process.id)
    assert process.state == ProcessState.COMPLETE
    assert "__error__" not in process.properties
    assert process.properties["__task_output_recover"] == "ok"
    assert "__task_output_happy" not in process.properties


async def test_successful_serial_workflow_still_completes(engine):
    process = await engine.create_process(_serial("ok"))
    await engine.start_process(process.id)
    process = await engine.store.load_process(process.id)
    assert process.state == ProcessState.COMPLETE
    assert "__error__" not in process.properties


async def test_parallel_branch_failure_fails_process_after_siblings_drain(engine):
    """A failed branch doesn't abort siblings; process FAILS once they drain."""
    defn = ProcessDefinition(
        id="parallel",
        name="Parallel",
        first_task_id="split",
        tasks={
            "split": TaskDefinition(id="split", name="Split", action="ok"),
            "calc": TaskDefinition(id="calc", name="Calc", action="fail"),
            "ask": TaskDefinition(id="ask", name="Ask", auto=False),
        },
        routings=[
            RoutingDefinition(id="r1", source_task_id="split", dest_task_id="calc", parallel=True),
            RoutingDefinition(id="r2", source_task_id="split", dest_task_id="ask", parallel=True),
        ],
    )
    process = await engine.create_process(defn)
    await engine.start_process(process.id)

    # Mid-drain: calc FAILED but the human branch is still open -> RUNNING, no error yet
    mid = await engine.store.load_process(process.id)
    assert mid.state == ProcessState.RUNNING
    assert "__error__" not in mid.properties

    (ask,) = await engine.get_pending_tasks(process.id)
    await engine.complete_task(ask.id, TaskResult.ok(output="done"))

    await _assert_failed(engine, process.id, "NameError: name 'x' is not defined")
