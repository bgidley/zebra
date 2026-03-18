"""Tests for GoalScheduler."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from zebra_agent.scheduler import GoalScheduler


def _make_process(
    process_id="p-1",
    priority=3,
    deadline=None,
    created_at=None,
    state="CREATED",
):
    """Helper to create a mock ProcessInstance."""
    p = MagicMock()
    p.id = process_id
    p.state = MagicMock(value=state)
    p.parent_process_id = None
    p.created_at = created_at or datetime.now(UTC)
    p.properties = {"priority": priority}
    if deadline:
        p.properties["deadline"] = deadline
    return p


@pytest.fixture
def mock_store():
    """Create a mock StateStore."""
    store = MagicMock()
    store.get_processes_by_state = AsyncMock(return_value=[])
    return store


@pytest.fixture
def scheduler(mock_store):
    return GoalScheduler(mock_store)


class TestScoreProcess:
    """Tests for score_process()."""

    def test_default_priority_score(self, scheduler):
        """Default priority (3) produces a base score of 300."""
        process = _make_process(priority=3, created_at=datetime.now(UTC))
        score = scheduler.score_process(process)
        # Priority 3 * 100 = 300, plus tiny age bonus
        assert 299 < score < 310

    def test_higher_priority_higher_score(self, scheduler):
        """Higher priority produces higher score."""
        now = datetime.now(UTC)
        low = _make_process(priority=1, created_at=now)
        high = _make_process(priority=5, created_at=now)
        assert scheduler.score_process(high) > scheduler.score_process(low)

    def test_priority_clamped(self, scheduler):
        """Priority is clamped to 1-5."""
        now = datetime.now(UTC)
        p_low = _make_process(priority=-1, created_at=now)
        p_high = _make_process(priority=99, created_at=now)
        # Clamped to 1 and 5 respectively
        score_low = scheduler.score_process(p_low)
        score_high = scheduler.score_process(p_high)
        assert score_low < 110  # ~100 (priority 1)
        assert score_high > 490  # ~500 (priority 5)

    def test_deadline_boosts_score(self, scheduler):
        """Approaching deadline boosts score."""
        now = datetime.now(UTC)
        no_deadline = _make_process(priority=3, created_at=now)
        with_deadline = _make_process(
            priority=3,
            deadline=(now + timedelta(hours=1)).isoformat(),
            created_at=now,
        )
        assert scheduler.score_process(with_deadline) > scheduler.score_process(no_deadline)

    def test_past_deadline_maximum_boost(self, scheduler):
        """Past deadline gives maximum urgency boost."""
        now = datetime.now(UTC)
        past = _make_process(
            priority=3,
            deadline=(now - timedelta(hours=1)).isoformat(),
            created_at=now,
        )
        future = _make_process(
            priority=3,
            deadline=(now + timedelta(hours=12)).isoformat(),
            created_at=now,
        )
        assert scheduler.score_process(past) > scheduler.score_process(future)

    def test_age_anti_starvation(self, scheduler):
        """Older processes get a higher score (anti-starvation)."""
        now = datetime.now(UTC)
        young = _make_process(priority=3, created_at=now)
        old = _make_process(priority=3, created_at=now - timedelta(hours=2))
        assert scheduler.score_process(old) > scheduler.score_process(young)

    def test_invalid_priority_defaults_to_3(self, scheduler):
        """Invalid priority string defaults to 3."""
        p = _make_process(priority="invalid", created_at=datetime.now(UTC))
        score = scheduler.score_process(p)
        # Should be same as priority 3
        assert 299 < score < 310

    def test_invalid_deadline_ignored(self, scheduler):
        """Invalid deadline string is ignored."""
        p = _make_process(
            priority=3,
            deadline="not-a-date",
            created_at=datetime.now(UTC),
        )
        score = scheduler.score_process(p)
        # Should be same as no deadline
        assert 299 < score < 310


class TestGetPendingGoals:
    """Tests for get_pending_goals()."""

    async def test_empty_queue(self, scheduler, mock_store):
        """Empty queue returns empty list."""
        mock_store.get_processes_by_state.return_value = []
        result = await scheduler.get_pending_goals()
        assert result == []

    async def test_returns_sorted_by_score(self, scheduler, mock_store):
        """Goals returned in descending score order."""
        now = datetime.now(UTC)
        p1 = _make_process("p-1", priority=1, created_at=now)
        p2 = _make_process("p-2", priority=5, created_at=now)
        p3 = _make_process("p-3", priority=3, created_at=now)
        mock_store.get_processes_by_state.return_value = [p1, p2, p3]

        result = await scheduler.get_pending_goals()
        assert [p.id for p in result] == ["p-2", "p-3", "p-1"]


class TestPickNext:
    """Tests for pick_next()."""

    async def test_pick_next_empty(self, scheduler, mock_store):
        """Empty queue returns None."""
        mock_store.get_processes_by_state.return_value = []
        result = await scheduler.pick_next()
        assert result is None

    async def test_pick_next_returns_highest(self, scheduler, mock_store):
        """Returns the highest-scored process."""
        now = datetime.now(UTC)
        p1 = _make_process("p-low", priority=1, created_at=now)
        p2 = _make_process("p-high", priority=5, created_at=now)
        mock_store.get_processes_by_state.return_value = [p1, p2]

        result = await scheduler.pick_next()
        assert result.id == "p-high"
