"""E2E tests for SchedulerLoop with a real workflow engine.

Uses InMemory stores and a FakeClock to test the full dispatch path
without wall-clock delays.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from zebra.core.engine import ActionRegistry, WorkflowEngine
from zebra.core.models import ProcessDefinition, ProcessState, TaskDefinition
from zebra.storage.memory import InMemoryStore

from zebra_agent.scheduler.loop import SchedulerLoop
from zebra_agent.scheduler.registry import RoutineRegistry
from zebra_agent.scheduler.routine import Routine, RoutineRun
from zebra_agent.scheduler.store import InMemoryRoutineRunStore
from zebra_agent.scheduler.testing import FakeClock

START = datetime(2026, 5, 4, 10, 0, 0, tzinfo=UTC)


def _make_noop_definition(workflow_name: str) -> ProcessDefinition:
    """Minimal single-task workflow that completes immediately."""
    task_def = TaskDefinition(
        id="t1",
        name="Noop Task",
        action="noop",
        auto=True,
    )
    return ProcessDefinition(
        id="test-wf",
        name=workflow_name,
        first_task_id="t1",
        tasks={"t1": task_def},
    )


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture
def workflow_engine(store):
    from zebra.tasks.base import TaskAction, TaskResult

    class NoopAction(TaskAction):
        async def run(self, task, context) -> TaskResult:
            return TaskResult.ok(output={"done": True})

    registry = ActionRegistry()
    registry.register_action("noop", NoopAction)
    engine = WorkflowEngine(store, registry)
    return engine


async def test_routine_fires_and_tags_process(workflow_engine):
    """End-to-end: FakeClock advances 1 min, routine fires, process is created and tagged."""
    store = InMemoryRoutineRunStore()
    registry = RoutineRegistry()
    clock = FakeClock(START)

    routine_name = "test_interval_routine"
    wf_name = "Test Workflow"

    # Register a workflow definition so the library can find it
    wf_def = _make_noop_definition(wf_name)

    # Inject a mock library that returns our definition
    from unittest.mock import AsyncMock, MagicMock

    library = MagicMock()
    library.get_workflow = AsyncMock(return_value=wf_def)
    workflow_engine.extras["__workflow_library__"] = library

    routine = Routine(name=routine_name, schedule={"every": "1m"}, workflow=wf_name)
    registry.register(routine)

    loop = SchedulerLoop(
        registry=registry,
        store=store,
        engine=workflow_engine,
        clock=clock,
    )

    # Set next_run to START + 1 minute so it's not due yet
    await store.upsert_run(
        RoutineRun(routine_name, last_run=START, next_run=START + timedelta(minutes=1))
    )

    # Tick at START — routine should NOT fire
    await loop._tick()
    all_processes = await workflow_engine.store.get_processes_by_state(ProcessState.CREATED)
    running = await workflow_engine.store.get_processes_by_state(ProcessState.RUNNING)
    complete = await workflow_engine.store.get_processes_by_state(ProcessState.COMPLETE)
    assert len(all_processes) + len(running) + len(complete) == 0

    # Advance clock by 1 minute — routine is now due
    clock.advance(minutes=1)
    await loop._tick()

    # A process should have been created (and may be COMPLETE already since noop is auto)
    process_id = None
    for state in (ProcessState.CREATED, ProcessState.RUNNING, ProcessState.COMPLETE):
        procs = await workflow_engine.store.get_processes_by_state(state)
        if procs:
            process_id = procs[0].id
            the_process = procs[0]
            break

    assert process_id is not None, "Expected a process to be created after routine fired"
    assert (the_process.properties or {}).get("__routine__") == routine_name


async def test_first_tick_fires_immediately(workflow_engine):
    """A routine with no persisted state fires on the very first tick."""
    store = InMemoryRoutineRunStore()
    registry = RoutineRegistry()
    clock = FakeClock(START)

    routine_name = "immediate_routine"
    wf_name = "Immediate Workflow"

    from unittest.mock import AsyncMock, MagicMock

    wf_def = _make_noop_definition(wf_name)
    library = MagicMock()
    library.get_workflow = AsyncMock(return_value=wf_def)
    workflow_engine.extras["__workflow_library__"] = library

    routine = Routine(name=routine_name, schedule={"every": "5m"}, workflow=wf_name)
    registry.register(routine)

    loop = SchedulerLoop(registry=registry, store=store, engine=workflow_engine, clock=clock)

    # No persisted state — should fire immediately
    await loop._tick()

    created = []
    for state in (ProcessState.CREATED, ProcessState.RUNNING, ProcessState.COMPLETE):
        created.extend(await workflow_engine.store.get_processes_by_state(state))

    assert any(p.properties and p.properties.get("__routine__") == routine_name for p in created), (
        "Expected routine process to be created on first tick"
    )
