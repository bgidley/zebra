"""Tests for BudgetManager."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zebra_agent.budget import BudgetManager


@pytest.fixture
def mock_metrics():
    """Create a mock metrics store with get_total_cost_since."""
    store = MagicMock()
    store.get_total_cost_since = AsyncMock(return_value=0.0)
    return store


@pytest.fixture
def budget(mock_metrics):
    """Create a BudgetManager with $50/day budget."""
    return BudgetManager(
        daily_budget_usd=50.0,
        metrics_store=mock_metrics,
        reset_hour=0,
        warning_threshold_usd=5.0,
    )


class TestBudgetManagerBasic:
    """Basic budget manager tests."""

    def test_init(self, budget):
        """Budget manager initializes correctly."""
        assert budget.daily_budget_usd == 50.0
        assert budget._reset_hour == 0
        assert budget._warning_threshold_usd == 5.0

    def test_budget_start_after_reset(self, budget):
        """Budget start is today's reset hour if past reset."""
        start = budget._budget_start()
        assert start.tzinfo is not None
        assert start.hour == 0
        assert start.minute == 0
        assert start.second == 0

    def test_hours_since_reset_positive(self, budget):
        """Hours since reset is non-negative."""
        hours = budget._hours_since_reset()
        assert hours >= 0


class TestBudgetManagerSpending:
    """Budget spending and allowance tests."""

    async def test_get_spent_today_delegates_to_store(self, budget, mock_metrics):
        """get_spent_today queries metrics store."""
        mock_metrics.get_total_cost_since.return_value = 12.50
        spent = await budget.get_spent_today()
        assert spent == 12.50
        mock_metrics.get_total_cost_since.assert_called_once()

    async def test_get_remaining_budget(self, budget, mock_metrics):
        """Remaining = daily - spent."""
        mock_metrics.get_total_cost_since.return_value = 10.0
        remaining = await budget.get_remaining_budget()
        assert remaining == 40.0

    async def test_remaining_can_be_negative(self, budget, mock_metrics):
        """Remaining budget can be negative if overspent."""
        mock_metrics.get_total_cost_since.return_value = 60.0
        remaining = await budget.get_remaining_budget()
        assert remaining == -10.0

    def test_paced_allowance_is_fraction(self, budget):
        """Paced allowance is a fraction of daily budget."""
        allowance = budget.get_paced_allowance()
        assert 0 <= allowance <= budget.daily_budget_usd

    async def test_get_available_budget(self, budget, mock_metrics):
        """Available = paced_allowance - spent."""
        mock_metrics.get_total_cost_since.return_value = 5.0
        available = await budget.get_available_budget()
        expected = budget.get_paced_allowance() - 5.0
        assert abs(available - expected) < 0.01


class TestBudgetManagerCanExecute:
    """can_execute() tests."""

    async def test_can_execute_when_budget_available(self, budget, mock_metrics):
        """Can execute when budget is available."""
        mock_metrics.get_total_cost_since.return_value = 0.0
        can = await budget.can_execute(estimated_cost=1.0)
        # Should be true unless we're at very start of day
        paced = budget.get_paced_allowance()
        assert can == (paced >= 1.0)

    async def test_cannot_execute_when_exhausted(self, budget, mock_metrics):
        """Cannot execute when budget is exhausted."""
        mock_metrics.get_total_cost_since.return_value = 999.0
        can = await budget.can_execute(estimated_cost=0.0)
        assert can is False

    async def test_can_execute_zero_estimate(self, budget, mock_metrics):
        """Zero-cost estimate: available just needs to be >= 0."""
        mock_metrics.get_total_cost_since.return_value = 0.0
        can = await budget.can_execute(estimated_cost=0.0)
        assert can is True


class TestBudgetManagerWarning:
    """check_and_warn() tests."""

    async def test_no_warning_under_threshold(self, budget, mock_metrics):
        """No warning when under threshold."""
        mock_metrics.get_total_cost_since.return_value = 0.0
        # Should not raise
        await budget.check_and_warn(current_run_cost=1.0)

    async def test_warning_over_threshold(self, budget, mock_metrics, caplog):
        """Warning logged when run cost exceeds threshold."""
        import logging

        mock_metrics.get_total_cost_since.return_value = 0.0
        with caplog.at_level(logging.WARNING, logger="zebra_agent.budget"):
            await budget.check_and_warn(current_run_cost=6.0)
        assert any("warning threshold" in r.message.lower() for r in caplog.records)


class TestBudgetManagerStatus:
    """get_status() tests."""

    async def test_status_has_required_keys(self, budget, mock_metrics):
        """Status dict has all required keys."""
        mock_metrics.get_total_cost_since.return_value = 5.0
        status = await budget.get_status()
        required_keys = {
            "daily_budget",
            "spent_today",
            "remaining",
            "paced_allowance",
            "available",
            "pct_used",
            "reset_hour",
            "hours_since_reset",
        }
        assert required_keys.issubset(set(status.keys()))

    async def test_status_values_correct(self, budget, mock_metrics):
        """Status values are consistent."""
        mock_metrics.get_total_cost_since.return_value = 10.0
        status = await budget.get_status()
        assert status["daily_budget"] == 50.0
        assert status["spent_today"] == 10.0
        assert status["remaining"] == 40.0
        assert status["reset_hour"] == 0
        assert "%" in status["pct_used"]

    async def test_status_pct_with_zero_budget(self, mock_metrics):
        """Percentage is 0% with zero budget (avoid division by zero)."""
        bm = BudgetManager(
            daily_budget_usd=0.0,
            metrics_store=mock_metrics,
        )
        mock_metrics.get_total_cost_since.return_value = 0.0
        status = await bm.get_status()
        assert status["pct_used"] == "0.0%"


class TestBudgetResetHour:
    """Budget reset hour edge cases."""

    def test_custom_reset_hour(self, mock_metrics):
        """Custom reset hour is respected."""
        bm = BudgetManager(
            daily_budget_usd=100.0,
            metrics_store=mock_metrics,
            reset_hour=6,
        )
        start = bm._budget_start()
        assert start.hour == 6
