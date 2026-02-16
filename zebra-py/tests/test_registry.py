"""Tests for ActionRegistry."""

import pytest
from zebra.tasks.registry import ActionRegistry
from zebra.tasks.base import TaskAction, ConditionAction, ExecutionContext, AlwaysTrueCondition
from zebra.core.models import TaskInstance, TaskResult
from zebra.core.exceptions import ActionNotFoundError


class DummyAction(TaskAction):
    """Dummy action for testing."""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        return TaskResult.ok(output="dummy")


class DummyCondition(ConditionAction):
    """Dummy condition for testing."""

    async def evaluate(self, task: TaskInstance, context: ExecutionContext) -> bool:
        return True


class TestActionRegistry:
    """Tests for ActionRegistry."""

    def test_register_and_get_action(self):
        """Test registering and getting an action."""
        registry = ActionRegistry()
        registry.register_action("dummy", DummyAction)

        action = registry.get_action("dummy")
        assert isinstance(action, DummyAction)

    def test_get_action_not_found(self):
        """Test getting non-existent action raises error."""
        registry = ActionRegistry()

        with pytest.raises(ActionNotFoundError, match="No task action"):
            registry.get_action("nonexistent")

    def test_register_invalid_action(self):
        """Test registering invalid action type raises error."""
        registry = ActionRegistry()

        with pytest.raises(TypeError, match="must be a TaskAction subclass"):
            registry.register_action("invalid", "not a class")

        with pytest.raises(TypeError, match="must be a TaskAction subclass"):
            registry.register_action("invalid", DummyCondition)  # Wrong type

    def test_has_action(self):
        """Test checking if action exists."""
        registry = ActionRegistry()
        registry.register_action("dummy", DummyAction)

        assert registry.has_action("dummy") is True
        assert registry.has_action("nonexistent") is False

    def test_list_actions(self):
        """Test listing registered actions."""
        registry = ActionRegistry()
        registry.register_action("action1", DummyAction)
        registry.register_action("action2", DummyAction)

        actions = registry.list_actions()
        assert "action1" in actions
        assert "action2" in actions

    def test_register_and_get_condition(self):
        """Test registering and getting a condition."""
        registry = ActionRegistry()
        registry.register_condition("dummy", DummyCondition)

        condition = registry.get_condition("dummy")
        assert isinstance(condition, DummyCondition)

    def test_get_condition_none_returns_always_true(self):
        """Test getting None condition returns AlwaysTrueCondition."""
        registry = ActionRegistry()

        condition = registry.get_condition(None)
        assert isinstance(condition, AlwaysTrueCondition)

    def test_get_condition_not_found(self):
        """Test getting non-existent condition raises error."""
        registry = ActionRegistry()

        with pytest.raises(ActionNotFoundError, match="No condition"):
            registry.get_condition("nonexistent")

    def test_register_invalid_condition(self):
        """Test registering invalid condition type raises error."""
        registry = ActionRegistry()

        with pytest.raises(TypeError, match="must be a ConditionAction subclass"):
            registry.register_condition("invalid", "not a class")

        with pytest.raises(TypeError, match="must be a ConditionAction subclass"):
            registry.register_condition("invalid", DummyAction)  # Wrong type

    def test_has_condition(self):
        """Test checking if condition exists."""
        registry = ActionRegistry()
        registry.register_condition("dummy", DummyCondition)

        assert registry.has_condition("dummy") is True
        assert registry.has_condition("nonexistent") is False
        assert registry.has_condition("always_true") is True  # Built-in

    def test_list_conditions(self):
        """Test listing registered conditions."""
        registry = ActionRegistry()
        registry.register_condition("cond1", DummyCondition)
        registry.register_condition("cond2", DummyCondition)

        conditions = registry.list_conditions()
        assert "cond1" in conditions
        assert "cond2" in conditions
        assert "always_true" in conditions  # Built-in

    def test_register_defaults(self):
        """Test registering default actions and conditions."""
        registry = ActionRegistry()
        registry.register_defaults()

        # Should have shell action (prompt was removed in human task cleanup)
        assert registry.has_action("shell")

        # Should have route_name condition
        assert registry.has_condition("route_name")

    def test_always_true_condition_builtin(self):
        """Test that always_true is registered by default."""
        registry = ActionRegistry()
        assert registry.has_condition("always_true")
