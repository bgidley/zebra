"""Routine and RoutineRun data models for the polling scheduler."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

from cronsim import CronSim


def _parse_interval(spec: str) -> timedelta:
    """Parse an ``every: Xs/Xm/Xh/Xd`` interval spec into a timedelta.

    Raises ValueError for unrecognised formats.
    """
    spec = spec.strip()
    if spec.endswith("s"):
        return timedelta(seconds=int(spec[:-1]))
    if spec.endswith("m"):
        return timedelta(minutes=int(spec[:-1]))
    if spec.endswith("h"):
        return timedelta(hours=int(spec[:-1]))
    if spec.endswith("d"):
        return timedelta(days=int(spec[:-1]))
    raise ValueError(f"Unrecognised interval spec: {spec!r}. Use Xs, Xm, Xh, or Xd.")


def next_run_for(
    schedule: str | dict,
    last_run: datetime | None,
    now: datetime,
) -> datetime:
    """Compute the next run time for a routine.

    Args:
        schedule: Either a cron string (``"0 3 * * *"``) or an interval dict
            (``{"every": "30m"}``).
        last_run: The last time the routine ran, or None if never.
        now: Current time (UTC).

    Returns:
        The next datetime at which the routine should run.
    """
    if isinstance(schedule, dict):
        interval = _parse_interval(schedule["every"])
        if last_run is None:
            return now
        return last_run + interval

    # Cron string
    cron = CronSim(schedule, now)
    return next(cron)


@dataclass
class Routine:
    """Definition of a scheduled routine."""

    name: str
    schedule: str | dict  # cron string OR {"every": "Xm/Xh/Xd"}
    workflow: str | None = None  # workflow name to create a process for; None = goal_queue_tick
    budget_aware: bool = False
    quiet_hours_ok: bool = True
    on_missed: Literal["skip", "catchup"] = "skip"
    description: str = ""
    extra_properties: dict = field(default_factory=dict)


@dataclass
class RoutineRun:
    """Persisted state for a single routine execution record."""

    routine_name: str
    last_run: datetime | None
    next_run: datetime
    last_status: str = "pending"

    @classmethod
    def initial(cls, routine: Routine, now: datetime) -> RoutineRun:
        """Create an initial RoutineRun (no prior run) — fires immediately."""
        return cls(
            routine_name=routine.name,
            last_run=None,
            next_run=now,
            last_status="pending",
        )

    def advance(self, routine: Routine, now: datetime, status: str = "ok") -> RoutineRun:
        """Return a new RoutineRun with updated last/next run times."""
        next_t = next_run_for(routine.schedule, now, now)
        return RoutineRun(
            routine_name=self.routine_name,
            last_run=now,
            next_run=next_t,
            last_status=status,
        )


def utc_now() -> datetime:
    return datetime.now(UTC)
