"""Action registry for managing task actions and conditions.

This module provides the ActionRegistry class that manages registration
and lookup of TaskAction and ConditionAction implementations.
"""

from typing import TypeVar

from zebra.core.exceptions import ActionNotFoundError
from zebra.tasks.base import AlwaysTrueCondition, ConditionAction, TaskAction

T = TypeVar("T", bound=TaskAction | ConditionAction)


class ActionRegistry:
    """Registry for task actions and routing conditions.

    Actions are registered by name and can be looked up later during
    workflow execution. This allows workflow definitions to reference
    actions by string name rather than Python class references.

    Example:
        registry = ActionRegistry()
        registry.register_action("shell", ShellTaskAction)
        registry.register_action("git", GitTaskAction)

        # Later, during execution:
        action = registry.get_action("shell")
        result = await action.run(task, context)
    """

    def __init__(self) -> None:
        self._actions: dict[str, type[TaskAction]] = {}
        self._conditions: dict[str, type[ConditionAction]] = {}

        # Register built-in conditions
        self._conditions["always_true"] = AlwaysTrueCondition

    # =========================================================================
    # Task Action Registration
    # =========================================================================

    def register_action(self, name: str, action_class: type[TaskAction]) -> None:
        """Register a task action by name.

        Args:
            name: The name to register the action under
            action_class: The TaskAction subclass to register

        Raises:
            TypeError: If action_class is not a TaskAction subclass
        """
        if not isinstance(action_class, type) or not issubclass(action_class, TaskAction):
            raise TypeError(f"action_class must be a TaskAction subclass, got {action_class}")
        self._actions[name] = action_class

    def get_action(self, name: str) -> TaskAction:
        """Get a task action instance by name.

        Args:
            name: The registered name of the action

        Returns:
            A new instance of the registered TaskAction

        Raises:
            ActionNotFoundError: If no action is registered with that name
        """
        if name not in self._actions:
            raise ActionNotFoundError(f"No task action registered with name '{name}'")
        return self._actions[name]()

    def has_action(self, name: str) -> bool:
        """Check if a task action is registered."""
        return name in self._actions

    def list_actions(self) -> list[str]:
        """List all registered task action names."""
        return list(self._actions.keys())

    # =========================================================================
    # Condition Registration
    # =========================================================================

    def register_condition(self, name: str, condition_class: type[ConditionAction]) -> None:
        """Register a routing condition by name.

        Args:
            name: The name to register the condition under
            condition_class: The ConditionAction subclass to register

        Raises:
            TypeError: If condition_class is not a ConditionAction subclass
        """
        if not isinstance(condition_class, type) or not issubclass(
            condition_class, ConditionAction
        ):
            raise TypeError(
                f"condition_class must be a ConditionAction subclass, got {condition_class}"
            )
        self._conditions[name] = condition_class

    def get_condition(self, name: str | None) -> ConditionAction:
        """Get a condition action instance by name.

        If name is None, returns an AlwaysTrueCondition.

        Args:
            name: The registered name of the condition, or None

        Returns:
            A new instance of the registered ConditionAction

        Raises:
            ActionNotFoundError: If no condition is registered with that name
        """
        if name is None:
            return AlwaysTrueCondition()
        if name not in self._conditions:
            raise ActionNotFoundError(f"No condition registered with name '{name}'")
        return self._conditions[name]()

    def has_condition(self, name: str) -> bool:
        """Check if a condition is registered."""
        return name in self._conditions

    def list_conditions(self) -> list[str]:
        """List all registered condition names."""
        return list(self._conditions.keys())

    # =========================================================================
    # Bulk Registration
    # =========================================================================

    def register_defaults(self) -> None:
        """Register all built-in actions.

        Call this to register the standard set of task actions
        (shell, prompt, etc.) and conditions.
        """
        # Import here to avoid circular imports
        from zebra.tasks.actions import get_default_actions, get_default_conditions

        for name, action_class in get_default_actions().items():
            self.register_action(name, action_class)

        for name, condition_class in get_default_conditions().items():
            self.register_condition(name, condition_class)
