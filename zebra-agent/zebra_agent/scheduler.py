"""GoalScheduler — pick the highest-priority CREATED process to execute.

Scoring considers:
- ``priority`` process property (1-5, default 3): higher → higher score
- ``deadline`` process property (ISO datetime): approaching deadlines boost score
- Age: older goals get a slight bump to prevent starvation
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zebra.core.models import ProcessInstance
    from zebra.storage.base import StateStore

logger = logging.getLogger(__name__)

# Weights for the scoring formula
_PRIORITY_WEIGHT = 100.0
_DEADLINE_WEIGHT = 50.0
_AGE_WEIGHT = 0.5  # per minute of age


class GoalScheduler:
    """Select the best CREATED process to start next."""

    def __init__(self, store: "StateStore") -> None:
        self._store = store

    async def get_pending_goals(self) -> list["ProcessInstance"]:
        """Return CREATED top-level processes, sorted by score descending."""
        from zebra.core.models import ProcessState

        processes = await self._store.get_processes_by_state(
            ProcessState.CREATED, exclude_children=True
        )
        scored = [(self.score_process(p), p) for p in processes]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [p for _, p in scored]

    def score_process(self, process: "ProcessInstance") -> float:
        """Compute a scheduling score for *process*.

        Higher scores are picked first.
        """
        props = process.properties or {}
        now = datetime.now(UTC)

        # --- Priority (1-5, default 3) ---
        try:
            priority = int(props.get("priority", 3))
        except (TypeError, ValueError):
            priority = 3
        priority = max(1, min(5, priority))
        score = priority * _PRIORITY_WEIGHT

        # --- Deadline boost ---
        deadline_str = props.get("deadline")
        if deadline_str:
            try:
                deadline = datetime.fromisoformat(str(deadline_str))
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=UTC)
                hours_remaining = (deadline - now).total_seconds() / 3600
                if hours_remaining <= 0:
                    # Past deadline — maximum urgency
                    score += _DEADLINE_WEIGHT * 10
                elif hours_remaining < 24:
                    # Within 24h — inversely proportional boost
                    score += _DEADLINE_WEIGHT * (24 - hours_remaining) / 24
            except (ValueError, TypeError):
                pass  # bad deadline — ignore

        # --- Age (anti-starvation) ---
        if process.created_at:
            age_minutes = (now - process.created_at).total_seconds() / 60
            score += age_minutes * _AGE_WEIGHT

        return score

    async def pick_next(self) -> "ProcessInstance | None":
        """Return the highest-scored CREATED process, or None if the queue is empty."""
        pending = await self.get_pending_goals()
        if not pending:
            return None
        chosen = pending[0]
        props = chosen.properties or {}
        logger.info(
            "Scheduler picked process %s (priority=%s, deadline=%s, score=%.1f)",
            chosen.id[:12],
            props.get("priority", 3),
            props.get("deadline", "none"),
            self.score_process(chosen),
        )
        return chosen
