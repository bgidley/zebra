"""Tests for routines that queue goals (F155)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from zebra.core.models import ProcessState

from zebra_agent.scheduler.loop import SchedulerLoop
from zebra_agent.scheduler.registry import RoutineRegistry
from zebra_agent.scheduler.routine import Routine, RoutineRun
from zebra_agent.scheduler.store import InMemoryRoutineRunStore
from zebra_agent.scheduler.testing import FakeClock

START = datetime(2026, 10, 10, 7, 0, 0, tzinfo=UTC)
ROUTINES_DIR = Path(__file__).parents[2] / "zebra-agent-web" / "fixtures" / "routines"

NEWS = Routine(
    name="daily_news_reading",
    schedule="0 7 * * *",
    goal="Read today's news",
    workflow="Daily News Reading",
)


def _process(routine_name: str | None, pid: str = "proc-pending-0001", age=timedelta(hours=1)):
    process = MagicMock()
    process.id = pid
    process.created_at = START - age
    process.properties = {"__routine__": routine_name} if routine_name else {}
    return process


def _engine(pending: dict[ProcessState, list] | None = None):
    pending = pending or {}
    engine = MagicMock()
    engine.extras = {}
    engine.store.get_processes_by_state = AsyncMock(
        side_effect=lambda state: pending.get(state, [])
    )
    engine.create_process = AsyncMock()
    engine.start_process = AsyncMock()
    return engine


@pytest.fixture
def store():
    return InMemoryRoutineRunStore()


async def _due_loop(store, engine, queue_goal_fn, routine=NEWS):
    registry = RoutineRegistry()
    registry.register(routine)
    await store.upsert_run(
        RoutineRun(routine.name, last_run=None, next_run=START - timedelta(seconds=1))
    )
    return SchedulerLoop(
        registry=registry,
        store=store,
        engine=engine,
        clock=FakeClock(START),
        queue_goal_fn=queue_goal_fn,
    )


async def test_due_goal_routine_queues_goal_once(store):
    engine = _engine()
    queue_goal_fn = AsyncMock(return_value=MagicMock(id="goal-proc-123456"))
    loop = await _due_loop(store, engine, queue_goal_fn)

    await loop._tick()
    await loop._tick()  # next run is tomorrow 07:00 — not due again

    queue_goal_fn.assert_awaited_once_with(NEWS)
    engine.create_process.assert_not_awaited()  # goal path, not direct workflow start
    run = await store.get_run("daily_news_reading")
    assert run.last_status == "ok"
    assert run.next_run == START + timedelta(days=1)


@pytest.mark.parametrize("state", [ProcessState.CREATED, ProcessState.RUNNING])
async def test_pending_goal_from_same_routine_is_not_queued_again(store, state):
    engine = _engine({state: [_process("other_routine", "x"), _process("daily_news_reading")]})
    queue_goal_fn = AsyncMock()
    loop = await _due_loop(store, engine, queue_goal_fn)

    await loop._tick()

    queue_goal_fn.assert_not_awaited()
    run = await store.get_run("daily_news_reading")
    assert run.last_status == "already_queued"
    assert run.next_run > START


async def test_stale_pending_goal_does_not_block_routine(store):
    """Yesterday's goal parked on an unanswered human task must not stop today's run."""
    stale = _process("daily_news_reading", age=timedelta(days=1))
    engine = _engine({ProcessState.RUNNING: [stale]})
    queue_goal_fn = AsyncMock(return_value=MagicMock(id="goal-proc-123456"))
    loop = await _due_loop(store, engine, queue_goal_fn)

    await loop._tick()

    queue_goal_fn.assert_awaited_once_with(NEWS)
    assert (await store.get_run("daily_news_reading")).last_status == "ok"


async def test_goal_routine_without_queue_fn_is_skipped(store):
    engine = _engine()
    loop = await _due_loop(store, engine, None)

    await loop._tick()

    engine.create_process.assert_not_awaited()
    assert (await store.get_run("daily_news_reading")).last_status == "skipped"


async def test_queue_goal_error_is_recorded(store):
    queue_goal_fn = AsyncMock(side_effect=ValueError("Agent Main Loop missing"))
    loop = await _due_loop(store, _engine(), queue_goal_fn)

    await loop._tick()

    assert (await store.get_run("daily_news_reading")).last_status == "error"


def test_shipped_daily_news_routine_yaml_parses():
    registry = RoutineRegistry()
    registry.load_yaml_dir(ROUTINES_DIR)

    routine = registry.get("daily_news_reading")
    assert routine is not None
    assert routine.schedule == "0 7 * * *"
    assert routine.goal and "news.kagi.com" in routine.goal
    assert routine.workflow == "Daily News Reading"
    assert routine.goal_priority == 3
    assert routine.run_as is None
    assert routine.budget_aware is True


def test_yaml_goal_fields(tmp_path):
    (tmp_path / "r.yaml").write_text(
        "name: r\nschedule: '0 6 * * *'\ngoal: Do a thing\ngoal_priority: 1\nrun_as: alice\n"
    )
    registry = RoutineRegistry()
    registry.load_yaml_dir(tmp_path)

    routine = registry.get("r")
    assert (routine.goal, routine.goal_priority, routine.run_as, routine.workflow) == (
        "Do a thing",
        1,
        "alice",
        None,
    )
