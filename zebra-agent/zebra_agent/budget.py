"""BudgetManager — daily dollar-based budget tracking with time-of-day pacing.

The BudgetManager is injected via IoC into ``engine.extras["__budget_manager__"]``
so that both the daemon loop and individual task actions (e.g. ``LLMCallAction``)
can consult it.

Budget is *stateless* — ``get_spent_today`` queries the ``MetricsStore`` for
the sum of ``WorkflowRun.cost`` completed since the last reset.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zebra_agent.storage.interfaces import MetricsStore

logger = logging.getLogger(__name__)


class BudgetManager:
    """Track daily LLM spend and enforce time-of-day pacing."""

    def __init__(
        self,
        daily_budget_usd: float,
        metrics_store: "MetricsStore",
        reset_hour: int = 0,
        warning_threshold_usd: float = 5.00,
    ) -> None:
        """
        Args:
            daily_budget_usd: Maximum spend per day in USD.
            metrics_store: Injected MetricsStore for querying cost history.
            reset_hour: Hour of day (0-23) when the budget resets.
            warning_threshold_usd: Per-run cost that triggers a soft warning.
        """
        self.daily_budget_usd = daily_budget_usd
        self._metrics = metrics_store
        self._reset_hour = reset_hour
        self._warning_threshold_usd = warning_threshold_usd

    # ------------------------------------------------------------------
    # Budget queries
    # ------------------------------------------------------------------

    def _budget_start(self) -> datetime:
        """Return the datetime when the current budget period started."""
        now = datetime.now(UTC)
        reset_today = now.replace(hour=self._reset_hour, minute=0, second=0, microsecond=0)
        if now >= reset_today:
            return reset_today
        # Before the reset hour — budget period started yesterday
        return reset_today - timedelta(days=1)

    def _hours_since_reset(self) -> float:
        """Hours elapsed since the budget period started."""
        delta = datetime.now(UTC) - self._budget_start()
        return delta.total_seconds() / 3600

    async def get_spent_today(self) -> float:
        """Total USD spent since the last budget reset."""
        return await self._metrics.get_total_cost_since(self._budget_start())

    async def get_remaining_budget(self) -> float:
        """``daily_budget - spent_today``. Can be negative (overspent)."""
        return self.daily_budget_usd - await self.get_spent_today()

    def get_paced_allowance(self) -> float:
        """How much budget *should* have been used by now (linear pacing).

        ``daily_budget * (hours_since_reset / 24)``

        At 6 am → 25 % of daily budget.
        At noon → 50 %.
        At 6 pm → 75 %.
        """
        fraction = min(self._hours_since_reset() / 24.0, 1.0)
        return self.daily_budget_usd * fraction

    async def get_available_budget(self) -> float:
        """``paced_allowance - spent_today``.  Positive means room to execute."""
        return self.get_paced_allowance() - await self.get_spent_today()

    async def can_execute(self, estimated_cost: float = 0.0) -> bool:
        """Return True if the paced budget allows another execution."""
        available = await self.get_available_budget()
        return available >= estimated_cost

    # ------------------------------------------------------------------
    # Soft warning (called from LLMCallAction)
    # ------------------------------------------------------------------

    async def check_and_warn(self, current_run_cost: float) -> None:
        """Log a warning if the current run's cost exceeds the threshold.

        This is a *soft* check — it never aborts execution.
        """
        if current_run_cost >= self._warning_threshold_usd:
            logger.warning(
                "Run cost $%.4f exceeds warning threshold $%.2f",
                current_run_cost,
                self._warning_threshold_usd,
            )

        available = await self.get_available_budget()
        if available < 0:
            logger.warning(
                "Daily paced budget exceeded by $%.4f (spent $%.4f of $%.2f paced allowance)",
                abs(available),
                await self.get_spent_today(),
                self.get_paced_allowance(),
            )

    # ------------------------------------------------------------------
    # Status (for API / dashboard)
    # ------------------------------------------------------------------

    async def get_status(self) -> dict:
        """Return a JSON-friendly budget status dict."""
        spent = await self.get_spent_today()
        paced = self.get_paced_allowance()
        remaining = self.daily_budget_usd - spent
        available = paced - spent
        pct = (spent / self.daily_budget_usd * 100) if self.daily_budget_usd > 0 else 0.0

        return {
            "daily_budget": self.daily_budget_usd,
            "spent_today": round(spent, 6),
            "remaining": round(remaining, 6),
            "paced_allowance": round(paced, 6),
            "available": round(available, 6),
            "pct_used": f"{pct:.1f}%",
            "reset_hour": self._reset_hour,
            "hours_since_reset": round(self._hours_since_reset(), 2),
        }
