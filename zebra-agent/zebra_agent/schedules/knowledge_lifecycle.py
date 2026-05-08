"""Scheduled routine factories for knowledge lifecycle management (F32).

These factory functions are registered as ``zebra.schedules`` entry points
and are discovered automatically by the RoutineRegistry.
"""

from zebra_agent.scheduler.routine import Routine


def knowledge_decay_daily() -> Routine:
    """Daily confidence decay for time-sensitive knowledge entries."""
    return Routine(
        name="knowledge_decay_daily",
        schedule={"every": "1d"},
        workflow="Knowledge Decay",
        budget_aware=False,
        quiet_hours_ok=True,
        description=(
            "Apply exponential confidence decay to time-sensitive personal knowledge entries"
        ),
    )


def knowledge_verification_weekly() -> Routine:
    """Weekly verification prompt for low-confidence knowledge entries."""
    return Routine(
        name="knowledge_verification_weekly",
        schedule={"every": "7d"},
        workflow="Knowledge Verification",
        budget_aware=True,
        quiet_hours_ok=False,
        description="Surface low-confidence or stale knowledge entries for human verification",
    )
