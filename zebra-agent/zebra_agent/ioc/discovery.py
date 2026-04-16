"""Entry point discovery for task actions and conditions.

Uses Python's standard entry points mechanism (PEP 621) to discover
TaskAction and ConditionAction classes registered by installed packages.

Entry point groups:
- ``zebra.tasks``: TaskAction subclasses
- ``zebra.conditions``: ConditionAction subclasses

Example pyproject.toml entry:
    [project.entry-points."zebra.tasks"]
    llm_call = "zebra_tasks.llm.action:LLMCallAction"
    file_read = "zebra_tasks.filesystem.read:FileReadAction"
"""

import logging
import sys
from importlib.metadata import entry_points
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zebra.tasks.base import ConditionAction, TaskAction

logger = logging.getLogger(__name__)

TASKS_GROUP = "zebra.tasks"
CONDITIONS_GROUP = "zebra.conditions"


def discover_actions() -> dict[str, type["TaskAction"]]:
    """Discover all registered task actions via entry points.

    Scans the ``zebra.tasks`` entry point group for TaskAction subclasses.
    Each entry point name becomes the action's registration name.

    Returns:
        Dict mapping action names to TaskAction classes.
    """
    if sys.version_info >= (3, 12):
        eps = entry_points(group=TASKS_GROUP)
    else:
        all_eps = entry_points()
        eps = all_eps.get(TASKS_GROUP, []) if isinstance(all_eps, dict) else all_eps.select(
            group=TASKS_GROUP
        )

    actions: dict[str, type[TaskAction]] = {}
    for ep in eps:
        try:
            action_class = ep.load()
            actions[ep.name] = action_class
            logger.debug("Discovered action '%s' from %s", ep.name, ep.value)
        except Exception:
            logger.warning("Failed to load action '%s' from %s", ep.name, ep.value, exc_info=True)

    return actions


def discover_conditions() -> dict[str, type["ConditionAction"]]:
    """Discover all registered conditions via entry points.

    Scans the ``zebra.conditions`` entry point group for ConditionAction subclasses.

    Returns:
        Dict mapping condition names to ConditionAction classes.
    """
    if sys.version_info >= (3, 12):
        eps = entry_points(group=CONDITIONS_GROUP)
    else:
        all_eps = entry_points()
        eps = all_eps.get(CONDITIONS_GROUP, []) if isinstance(all_eps, dict) else all_eps.select(
            group=CONDITIONS_GROUP
        )

    conditions: dict[str, type[ConditionAction]] = {}
    for ep in eps:
        try:
            condition_class = ep.load()
            conditions[ep.name] = condition_class
            logger.debug("Discovered condition '%s' from %s", ep.name, ep.value)
        except Exception:
            logger.warning(
                "Failed to load condition '%s' from %s", ep.name, ep.value, exc_info=True
            )

    return conditions
