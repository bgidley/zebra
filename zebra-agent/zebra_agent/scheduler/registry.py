"""RoutineRegistry — discover and hold routine definitions."""

from __future__ import annotations

import importlib.metadata
import logging
from pathlib import Path

import yaml

from zebra_agent.scheduler.routine import Routine

logger = logging.getLogger(__name__)


class RoutineRegistry:
    """Discover and hold Routine definitions.

    Sources (merged, later sources override earlier by name):
    1. Built-in entry points registered under ``zebra.schedules``
    2. YAML files from a ``routines_dir`` directory (``*.yaml``)
    """

    def __init__(self) -> None:
        self._routines: dict[str, Routine] = {}

    def register(self, routine: Routine) -> None:
        """Register a single routine, replacing any existing one with the same name."""
        self._routines[routine.name] = routine

    def all(self) -> list[Routine]:
        return list(self._routines.values())

    def get(self, name: str) -> Routine | None:
        return self._routines.get(name)

    def load_entry_points(self) -> None:
        """Discover and register routines from ``zebra.schedules`` entry points."""
        try:
            eps = importlib.metadata.entry_points(group="zebra.schedules")
        except Exception:
            logger.debug("No zebra.schedules entry points found")
            return

        for ep in eps:
            try:
                factory = ep.load()
                routine = factory()
                if not isinstance(routine, Routine):
                    logger.warning(
                        "Entry point %s did not return a Routine (got %s)", ep.name, type(routine)
                    )
                    continue
                self.register(routine)
                logger.debug("Loaded routine from entry point: %s", routine.name)
            except Exception:
                logger.warning("Failed to load routine from entry point %s", ep.name, exc_info=True)

    def load_yaml_dir(self, routines_dir: str | Path) -> None:
        """Load routine definitions from all ``*.yaml`` files in *routines_dir*.

        Files with missing required fields are skipped with a warning.
        """
        path = Path(routines_dir)
        if not path.is_dir():
            logger.debug("Routines directory not found: %s", path)
            return

        for yaml_file in sorted(path.glob("*.yaml")):
            self._load_yaml_file(yaml_file)

    def _load_yaml_file(self, yaml_file: Path) -> None:
        try:
            with yaml_file.open() as f:
                data = yaml.safe_load(f)
        except Exception:
            logger.warning("Failed to parse routine YAML %s", yaml_file, exc_info=True)
            return

        if not isinstance(data, dict):
            logger.warning("Routine YAML %s is not a mapping — skipping", yaml_file)
            return

        name = data.get("name")
        schedule = data.get("schedule")
        if not name or not schedule:
            logger.warning(
                "Routine YAML %s missing required fields (name, schedule) — skipping", yaml_file
            )
            return

        # Normalise schedule: plain string → cron; dict with 'every' key → interval
        if isinstance(schedule, str):
            sched: str | dict = schedule
        elif isinstance(schedule, dict) and "every" in schedule:
            sched = schedule
        else:
            logger.warning("Routine YAML %s has unrecognised schedule format — skipping", yaml_file)
            return

        routine = Routine(
            name=name,
            schedule=sched,
            workflow=data.get("workflow"),
            budget_aware=bool(data.get("budget_aware", False)),
            quiet_hours_ok=bool(data.get("quiet_hours_ok", True)),
            on_missed=data.get("on_missed", "skip"),
            description=data.get("description", ""),
            extra_properties=data.get("extra_properties", {}),
        )
        self.register(routine)
        logger.debug("Loaded routine from YAML: %s (%s)", routine.name, yaml_file.name)
