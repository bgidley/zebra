"""Testing utilities for the scheduler."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


class FakeClock:
    """Deterministic clock for testing.

    Usage::

        clock = FakeClock(datetime(2026, 5, 4, 10, 0, 0, tzinfo=UTC))
        loop = SchedulerLoop(..., clock=clock)
        clock.advance(minutes=1)
    """

    def __init__(self, now: datetime | None = None) -> None:
        self._now = now or datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self._now

    def advance(self, *, seconds: int = 0, minutes: int = 0, hours: int = 0) -> None:
        self._now += timedelta(seconds=seconds, minutes=minutes, hours=hours)

    @property
    def now(self) -> datetime:
        return self._now
