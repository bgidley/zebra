"""RoutineRunStore — abstract interface and in-memory implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod

from zebra_agent.scheduler.routine import RoutineRun


class RoutineRunStore(ABC):
    """Persist last/next run state for scheduled routines."""

    @abstractmethod
    async def get_run(self, routine_name: str) -> RoutineRun | None:
        """Return the persisted RoutineRun for *routine_name*, or None if never run."""

    @abstractmethod
    async def upsert_run(self, run: RoutineRun) -> None:
        """Insert or update the RoutineRun record."""


class InMemoryRoutineRunStore(RoutineRunStore):
    """In-memory implementation for tests."""

    def __init__(self) -> None:
        self._runs: dict[str, RoutineRun] = {}

    async def get_run(self, routine_name: str) -> RoutineRun | None:
        return self._runs.get(routine_name)

    async def upsert_run(self, run: RoutineRun) -> None:
        self._runs[run.routine_name] = run
