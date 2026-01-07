"""Built-in task actions for common operations."""

from zebra.tasks.actions.prompt import PromptTaskAction
from zebra.tasks.actions.shell import ShellTaskAction
from zebra.tasks.base import ConditionAction, RouteNameCondition, TaskAction


def get_default_actions() -> dict[str, type[TaskAction]]:
    """Get the default set of task actions."""
    return {
        "shell": ShellTaskAction,
        "prompt": PromptTaskAction,
    }


def get_default_conditions() -> dict[str, type[ConditionAction]]:
    """Get the default set of routing conditions."""
    return {
        "route_name": RouteNameCondition,
    }


__all__ = [
    "ShellTaskAction",
    "PromptTaskAction",
    "get_default_actions",
    "get_default_conditions",
]
