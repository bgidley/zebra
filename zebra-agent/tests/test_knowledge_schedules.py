"""Tests for knowledge lifecycle scheduled routines."""

from zebra_agent.scheduler.registry import RoutineRegistry
from zebra_agent.scheduler.routine import Routine
from zebra_agent.schedules.knowledge_lifecycle import (
    knowledge_decay_daily,
    knowledge_verification_weekly,
)


def test_decay_factory_returns_routine():
    routine = knowledge_decay_daily()
    assert isinstance(routine, Routine)
    assert routine.name == "knowledge_decay_daily"
    assert routine.workflow == "Knowledge Decay"


def test_verification_factory_returns_routine():
    routine = knowledge_verification_weekly()
    assert isinstance(routine, Routine)
    assert routine.name == "knowledge_verification_weekly"
    assert routine.workflow == "Knowledge Verification"


def test_decay_schedule_is_daily():
    routine = knowledge_decay_daily()
    assert routine.schedule == {"every": "1d"}


def test_verification_schedule_is_weekly():
    routine = knowledge_verification_weekly()
    assert routine.schedule == {"every": "7d"}


def test_routines_discovered_via_entry_points():
    """Both routines appear after loading zebra.schedules entry points."""
    registry = RoutineRegistry()
    registry.load_entry_points()
    names = {r.name for r in registry.all()}
    assert "knowledge_decay_daily" in names
    assert "knowledge_verification_weekly" in names
