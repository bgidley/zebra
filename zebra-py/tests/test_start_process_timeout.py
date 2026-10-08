"""Tests for WorkflowEngine.start_process_with_timeout (#142).

start_process() runs auto tasks inline, so without a bound a hung action blocks
the caller forever. These tests use a slow action to prove the chain is cancelled
and the process failed at the deadline, on a cancel_check, and on caller cancel.
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


class SleepAction(TaskAction):
    """Sleeps for the task's ``seconds`` property, then succeeds."""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        await asyncio.sleep(float(task.properties.get("seconds", 0)))
        return TaskResult.ok(output={"slept": True})


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture
def engine(store):
    reg = ActionRegistry()
    reg.register_action("sleep", SleepAction)
    return WorkflowEngine(store, reg)


def _definition(seconds: float, manual_tail: bool = False) -> ProcessDefinition:
    tasks = {
        "work": TaskDefinition(
            id="work", name="Work", action="sleep", properties={"seconds": seconds}
        ),
        "after": TaskDefinition(id="after", name="After", action="sleep", auto=not manual_tail),
    }
    return ProcessDefinition(
        id=f"sleepy-{seconds}-{manual_tail}",
        name="Sleepy",
        first_task_id="work",
        tasks=tasks,
        routings=[RoutingDefinition(id="r1", source_task_id="work", dest_task_id="after")],
    )


async def _start(engine: WorkflowEngine, definition: ProcessDefinition) -> str:
    process = await engine.create_process(definition)
    return process.id


async def test_fast_process_completes_within_timeout(engine):
    pid = await _start(engine, _definition(0))

    process = await engine.start_process_with_timeout(pid, timeout=5)

    assert process.state == ProcessState.COMPLETE


async def test_slow_process_is_failed_at_timeout(engine, store):
    pid = await _start(engine, _definition(30))

    loop = asyncio.get_running_loop()
    began = loop.time()
    process = await engine.start_process_with_timeout(pid, timeout=0.2)

    assert loop.time() - began < 5
    assert process.state == ProcessState.FAILED
    assert "Timed out after 0.2s" in process.properties["__error__"]
    tasks = await store.load_tasks_for_process(pid)
    assert tasks and all(t.state == TaskState.FAILED for t in tasks)


async def test_lock_is_released_after_timeout(engine, store):
    pid = await _start(engine, _definition(30))

    await engine.start_process_with_timeout(pid, timeout=0.1)

    assert await store.acquire_lock(pid, "someone-else", 1.0)


async def test_cancel_check_reason_fails_process(engine):
    pid = await _start(engine, _definition(30))
    calls = 0

    async def cancel_check() -> str | None:
        nonlocal calls
        calls += 1
        return "Kill switch activated" if calls >= 2 else None

    process = await engine.start_process_with_timeout(
        pid, timeout=30, cancel_check=cancel_check, poll_interval=0.05
    )

    assert process.state == ProcessState.FAILED
    assert process.properties["__error__"] == "Kill switch activated"


async def test_manual_task_pause_returns_running_process(engine):
    """Parking on a manual task returns normally; the timeout does not fail it later."""
    pid = await _start(engine, _definition(0, manual_tail=True))

    process = await engine.start_process_with_timeout(pid, timeout=0.5)
    await asyncio.sleep(0.6)

    assert process.state == ProcessState.RUNNING
    assert (await engine.store.load_process(pid)).state == ProcessState.RUNNING


async def test_caller_cancellation_fails_process(engine):
    pid = await _start(engine, _definition(30))

    outer = asyncio.create_task(engine.start_process_with_timeout(pid, timeout=30))
    await asyncio.sleep(0.1)
    outer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await outer

    process = await engine.store.load_process(pid)
    assert process.state == ProcessState.FAILED
    assert process.properties["__error__"] == "Cancelled by caller"
