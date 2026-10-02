"""Tests for manual-review recovery: retry_task and the interrupted-attempt cap (#130)."""

import pytest

from zebra.core.engine import MANUAL_REVIEW_FLAG, WorkflowEngine
from zebra.core.exceptions import InvalidStateTransitionError
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


class SimulatedCrash(BaseException):
    """Escapes the engine's ``except Exception`` like a real process kill would."""


class CrashOnceAction(TaskAction):
    """Crashes mid-run while ``crash`` is set, otherwise succeeds."""

    crash = True
    calls = 0

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        type(self).calls += 1
        if type(self).crash:
            raise SimulatedCrash()
        return TaskResult.ok(output="side effect done")


@pytest.fixture(autouse=True)
def _reset_action():
    CrashOnceAction.crash = True
    CrashOnceAction.calls = 0


@pytest.fixture
def engine():
    registry = ActionRegistry()
    registry.register_action("crash_once", CrashOnceAction)
    return WorkflowEngine(InMemoryStore(), registry)


@pytest.fixture
def definition():
    return ProcessDefinition(
        id="side_effects",
        name="Side Effects",
        first_task_id="work",
        tasks={
            "work": TaskDefinition(id="work", name="Do Work", action="crash_once"),
            "done": TaskDefinition(id="done", name="Done"),
        },
        routings=[RoutingDefinition(id="r1", source_task_id="work", dest_task_id="done")],
    )


async def _interrupted_process(engine: WorkflowEngine, definition: ProcessDefinition):
    """Start a process whose first task is killed mid-run (left RUNNING with a token)."""
    process = await engine.create_process(definition)
    with pytest.raises(SimulatedCrash):
        await engine.start_process(process.id)
    [task] = await engine.store.get_running_tasks(process.id)
    assert task.properties.get("__idempotency_token__")
    return process, task


async def test_recovery_flags_interrupted_non_idempotent_task(engine, definition):
    process, task = await _interrupted_process(engine, definition)

    resumed = await engine.resume_all_processes()

    assert [p.id for p in resumed] == [process.id]
    flagged = await engine.store.load_task(task.id)
    assert flagged.state == TaskState.RUNNING
    assert flagged.properties[MANUAL_REVIEW_FLAG] is True
    assert flagged.execution_attempt == 1


async def test_retry_task_reruns_flagged_task_and_completes_process(engine, definition):
    process, task = await _interrupted_process(engine, definition)
    await engine.resume_all_processes()
    CrashOnceAction.crash = False

    reset = await engine.retry_task(task.id)

    assert reset.state == TaskState.READY
    assert MANUAL_REVIEW_FLAG not in reset.properties
    assert CrashOnceAction.calls == 2
    process = await engine.store.load_process(process.id)
    assert process.state == ProcessState.COMPLETE
    assert process.properties["__task_output_work"] == "side effect done"


async def test_retry_task_without_execute_only_resets(engine, definition):
    process, task = await _interrupted_process(engine, definition)
    await engine.resume_all_processes()

    await engine.retry_task(task.id, execute=False)

    reloaded = await engine.store.load_task(task.id)
    assert reloaded.state == TaskState.READY
    assert MANUAL_REVIEW_FLAG not in reloaded.properties
    assert CrashOnceAction.calls == 1
    assert (await engine.store.load_process(process.id)).state == ProcessState.RUNNING


async def test_retry_task_rejects_unflagged_task(engine, definition):
    _, task = await _interrupted_process(engine, definition)

    # Still RUNNING but recovery hasn't flagged it
    with pytest.raises(InvalidStateTransitionError):
        await engine.retry_task(task.id)


async def test_retry_task_rejects_task_of_failed_process(engine, definition):
    process, task = await _interrupted_process(engine, definition)
    await engine.resume_all_processes()
    flagged = await engine.store.load_task(task.id)
    # Process failed out from under the flagged task
    failed = (await engine.store.load_process(process.id)).model_copy(
        update={"state": ProcessState.FAILED}
    )
    await engine.store.save_process(failed)
    await engine.store.save_task(flagged)

    with pytest.raises(InvalidStateTransitionError):
        await engine.retry_task(task.id)


async def test_recovery_cap_fails_process_after_max_interruptions(engine, definition):
    process, task = await _interrupted_process(engine, definition)

    # Interruptions 1 and 2 flag; the 3rd hits the cap
    for attempt in (1, 2):
        resumed = await engine.resume_all_processes(max_interrupted_attempts=3)
        assert [p.id for p in resumed] == [process.id]
        assert (await engine.store.load_task(task.id)).execution_attempt == attempt

    resumed = await engine.resume_all_processes(max_interrupted_attempts=3)

    assert resumed == []
    failed = await engine.store.load_process(process.id)
    assert failed.state == ProcessState.FAILED
    error = failed.properties["__error__"]
    assert "Do Work" in error
    assert "interrupted 3 times" in error
    assert (await engine.store.load_task(task.id)).state == TaskState.FAILED
    # A failed process is no longer picked up by recovery
    assert await engine.resume_all_processes(max_interrupted_attempts=3) == []


async def test_recovery_cap_applies_to_idempotent_tasks(engine):
    definition = ProcessDefinition(
        id="idempotent",
        name="Idempotent",
        first_task_id="work",
        tasks={
            "work": TaskDefinition(
                id="work", name="Do Work", action="crash_once", properties={"idempotent": True}
            ),
        },
        routings=[],
    )
    process, _ = await _interrupted_process(engine, definition)

    # Idempotent tasks are re-run on resume (and crash again) until the cap trips
    for _ in range(2):
        with pytest.raises(SimulatedCrash):
            await engine.resume_all_processes(max_interrupted_attempts=3)

    assert await engine.resume_all_processes(max_interrupted_attempts=3) == []
    assert (await engine.store.load_process(process.id)).state == ProcessState.FAILED


async def test_recovery_without_cap_keeps_flagging(engine, definition):
    process, task = await _interrupted_process(engine, definition)

    for _ in range(5):
        await engine.resume_all_processes()

    flagged = await engine.store.load_task(task.id)
    assert flagged.execution_attempt == 5
    assert flagged.properties[MANUAL_REVIEW_FLAG] is True
    assert (await engine.store.load_process(process.id)).state == ProcessState.RUNNING
