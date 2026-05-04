"""Tests for InMemoryRoutineRunStore."""

from datetime import UTC, datetime, timedelta

import pytest

from zebra_agent.scheduler.routine import RoutineRun
from zebra_agent.scheduler.store import InMemoryRoutineRunStore


@pytest.fixture
def store():
    return InMemoryRoutineRunStore()


NOW = datetime(2026, 5, 4, 10, 0, 0, tzinfo=UTC)


async def test_get_run_missing(store):
    """Returns None for unknown routine."""
    result = await store.get_run("nonexistent")
    assert result is None


async def test_upsert_then_get(store):
    """Can store and retrieve a RoutineRun."""
    run = RoutineRun(
        routine_name="test_routine",
        last_run=None,
        next_run=NOW,
        last_status="pending",
    )
    await store.upsert_run(run)
    retrieved = await store.get_run("test_routine")
    assert retrieved is not None
    assert retrieved.routine_name == "test_routine"
    assert retrieved.next_run == NOW
    assert retrieved.last_run is None
    assert retrieved.last_status == "pending"


async def test_upsert_overwrites(store):
    """Second upsert replaces the first."""
    run1 = RoutineRun("r", None, NOW, "pending")
    run2 = RoutineRun("r", NOW, NOW + timedelta(hours=1), "ok")
    await store.upsert_run(run1)
    await store.upsert_run(run2)
    result = await store.get_run("r")
    assert result.last_run == NOW
    assert result.last_status == "ok"
