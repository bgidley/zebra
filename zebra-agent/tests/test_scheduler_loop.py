"""Tests for SchedulerLoop and FakeClock."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from zebra_agent.scheduler.loop import SchedulerLoop
from zebra_agent.scheduler.registry import RoutineRegistry
from zebra_agent.scheduler.routine import Routine, RoutineRun
from zebra_agent.scheduler.store import InMemoryRoutineRunStore
from zebra_agent.scheduler.testing import FakeClock

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

START = datetime(2026, 5, 4, 10, 0, 0, tzinfo=UTC)


def _make_engine(workflow_def=None):
    engine = MagicMock()
    engine.store = MagicMock()
    engine.extras = {}
    engine.create_process = AsyncMock(return_value=MagicMock(id="proc-1234567890"))
    engine.start_process = AsyncMock()
    return engine


def _make_loop(registry, store, engine, clock, budget_manager=None):
    return SchedulerLoop(
        registry=registry,
        store=store,
        engine=engine,
        budget_manager=budget_manager,
        clock=clock,
        poll_interval=30,
    )


# ---------------------------------------------------------------------------
# FakeClock
# ---------------------------------------------------------------------------


class TestFakeClock:
    def test_initial_time(self):
        clock = FakeClock(START)
        assert clock() == START

    def test_advance_seconds(self):
        clock = FakeClock(START)
        clock.advance(seconds=90)
        assert clock() == START + timedelta(seconds=90)

    def test_advance_minutes(self):
        clock = FakeClock(START)
        clock.advance(minutes=1)
        assert clock() == START + timedelta(minutes=1)

    def test_advance_hours(self):
        clock = FakeClock(START)
        clock.advance(hours=2)
        assert clock() == START + timedelta(hours=2)

    def test_advance_accumulates(self):
        clock = FakeClock(START)
        clock.advance(minutes=1)
        clock.advance(minutes=1)
        assert clock() == START + timedelta(minutes=2)


# ---------------------------------------------------------------------------
# SchedulerLoop tick behaviour
# ---------------------------------------------------------------------------


class TestSchedulerLoopTick:
    @pytest.fixture
    def store(self):
        return InMemoryRoutineRunStore()

    @pytest.fixture
    def clock(self):
        return FakeClock(START)

    async def test_due_routine_dispatched(self, store, clock):
        """A routine that is due fires and creates a process."""
        registry = RoutineRegistry()
        routine = Routine(name="test_r", schedule={"every": "1m"}, workflow="my_wf")
        registry.register(routine)

        engine = _make_engine()
        library = MagicMock()
        library.get_workflow = AsyncMock(return_value=MagicMock(name="my_wf"))
        engine.extras["__workflow_library__"] = library

        loop = _make_loop(registry, store, engine, clock)

        # Seed with a next_run in the past so it fires immediately
        await store.upsert_run(
            RoutineRun("test_r", last_run=None, next_run=START - timedelta(seconds=1))
        )

        await loop._tick()

        engine.create_process.assert_awaited_once()
        engine.start_process.assert_awaited_once()
        # Check __routine__ property was set
        call_kwargs = engine.create_process.call_args.kwargs
        assert call_kwargs["properties"]["__routine__"] == "test_r"

    async def test_not_due_routine_skipped(self, store, clock):
        """A routine whose next_run is in the future is not dispatched."""
        registry = RoutineRegistry()
        routine = Routine(name="future_r", schedule={"every": "1h"}, workflow="wf")
        registry.register(routine)

        engine = _make_engine()
        loop = _make_loop(registry, store, engine, clock)

        await store.upsert_run(
            RoutineRun("future_r", last_run=None, next_run=START + timedelta(hours=1))
        )

        await loop._tick()

        engine.create_process.assert_not_awaited()
        engine.start_process.assert_not_awaited()

    async def test_budget_exhausted_routine_skipped(self, store, clock):
        """A budget_aware routine is skipped when available budget is 0."""
        registry = RoutineRegistry()
        routine = Routine(
            name="expensive_r", schedule={"every": "30m"}, workflow="wf", budget_aware=True
        )
        registry.register(routine)

        engine = _make_engine()
        budget_manager = MagicMock()
        budget_manager.get_status = AsyncMock(return_value={"available": 0.0, "spent_today": 50.0})
        loop = _make_loop(registry, store, engine, clock, budget_manager=budget_manager)

        await store.upsert_run(
            RoutineRun("expensive_r", last_run=None, next_run=START - timedelta(seconds=1))
        )

        await loop._tick()

        engine.create_process.assert_not_awaited()
        # But next_run should have been updated to avoid re-checking every tick
        run = await store.get_run("expensive_r")
        assert run.last_status == "budget_skip"

    async def test_first_run_no_persisted_state(self, store, clock):
        """A routine with no persisted state fires immediately (next_run = now)."""
        registry = RoutineRegistry()
        routine = Routine(name="new_r", schedule={"every": "1m"}, workflow="wf")
        registry.register(routine)

        engine = _make_engine()
        library = MagicMock()
        library.get_workflow = AsyncMock(return_value=MagicMock(name="wf"))
        engine.extras["__workflow_library__"] = library

        loop = _make_loop(registry, store, engine, clock)

        await loop._tick()

        engine.create_process.assert_awaited_once()

    async def test_fake_clock_controls_due_check(self, store, clock):
        """FakeClock advancing 1 minute makes an every:1m routine due."""
        registry = RoutineRegistry()
        routine = Routine(name="timed_r", schedule={"every": "1m"}, workflow="wf")
        registry.register(routine)

        engine = _make_engine()
        library = MagicMock()
        library.get_workflow = AsyncMock(return_value=MagicMock(name="wf"))
        engine.extras["__workflow_library__"] = library

        loop = _make_loop(registry, store, engine, clock)

        # Set next_run to START + 1 minute (future from START)
        await store.upsert_run(
            RoutineRun("timed_r", last_run=START, next_run=START + timedelta(minutes=1))
        )

        # Tick at START — should not fire
        await loop._tick()
        engine.create_process.assert_not_awaited()

        # Advance clock by 1 minute — now it's due
        clock.advance(minutes=1)
        await loop._tick()
        engine.create_process.assert_awaited_once()

    async def test_run_state_persisted_after_dispatch(self, store, clock):
        """After dispatch, last_run and next_run are updated in the store."""
        registry = RoutineRegistry()
        routine = Routine(name="persist_r", schedule={"every": "30m"}, workflow="wf")
        registry.register(routine)

        engine = _make_engine()
        library = MagicMock()
        library.get_workflow = AsyncMock(return_value=MagicMock(name="wf"))
        engine.extras["__workflow_library__"] = library

        loop = _make_loop(registry, store, engine, clock)

        await store.upsert_run(
            RoutineRun("persist_r", last_run=None, next_run=START - timedelta(seconds=1))
        )

        await loop._tick()

        run = await store.get_run("persist_r")
        assert run.last_run is not None
        assert run.next_run > START
        assert run.last_status == "ok"
