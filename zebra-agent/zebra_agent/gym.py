"""Golden tasks for the self-improvement gym (#171).

A golden task is a curated goal with an expected outcome and scoring criteria,
tied to the workflow it exercises. The ``run_golden_gym`` action runs them to
score workflows and to block a self-modified workflow that scores worse than
the version it would replace. Golden tasks live as YAML files in
``zebra-agent/golden/`` (one per task), overridable by ``ZEBRA_GOLDEN_TASKS_DIR``.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

#: Environment variable overriding the golden task directory.
GOLDEN_DIR_ENV = "ZEBRA_GOLDEN_TASKS_DIR"

#: Built-in golden tasks, next to the built-in workflows.
DEFAULT_GOLDEN_DIR = Path(__file__).resolve().parent.parent / "golden"


@dataclass(frozen=True)
class GoldenTask:
    """A curated goal used to score a workflow."""

    id: str
    workflow: str  # Workflow name, as in its YAML ``name``
    goal: str
    expected: str
    criteria: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict."""
        return {
            "id": self.id,
            "workflow": self.workflow,
            "goal": self.goal,
            "expected": self.expected,
            "criteria": list(self.criteria),
        }


def golden_dir() -> Path:
    """Return the golden task directory (``ZEBRA_GOLDEN_TASKS_DIR`` or the built-in one)."""
    override = os.environ.get(GOLDEN_DIR_ENV)
    return Path(override).expanduser() if override else DEFAULT_GOLDEN_DIR


def parse_golden_task(data: Any) -> GoldenTask:
    """Build a GoldenTask from parsed YAML.

    Raises:
        ValueError: If a required field is missing or there are no criteria.
    """
    if not isinstance(data, dict):
        raise ValueError("not a mapping")
    values = {}
    for key in ("id", "workflow", "goal", "expected"):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"missing '{key}'")
        values[key] = value.strip()
    criteria = data.get("criteria")
    if not isinstance(criteria, list):
        raise ValueError("'criteria' must be a list")
    criteria = [str(c).strip() for c in criteria if str(c).strip()]
    if not criteria:
        raise ValueError("no criteria")
    return GoldenTask(criteria=criteria, **values)


def load_golden_tasks(directory: Path | None = None) -> list[GoldenTask]:
    """Load every valid golden task in *directory*, sorted by id.

    Invalid files and duplicate ids are skipped with a warning.
    """
    directory = directory or golden_dir()
    if not directory.is_dir():
        return []
    tasks: dict[str, GoldenTask] = {}
    for path in sorted(directory.glob("*.yaml")):
        try:
            task = parse_golden_task(yaml.safe_load(path.read_text()))
        except (yaml.YAMLError, ValueError, OSError) as e:
            logger.warning("Skipping golden task %s: %s", path.name, e)
            continue
        if task.id in tasks:
            logger.warning("Skipping golden task %s: duplicate id %r", path.name, task.id)
            continue
        tasks[task.id] = task
    return [tasks[k] for k in sorted(tasks)]
