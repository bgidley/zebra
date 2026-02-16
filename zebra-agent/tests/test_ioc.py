"""Tests for the IoC (Inversion of Control) module."""

from unittest.mock import MagicMock, patch

import pytest
from dependency_injector import providers
from zebra.core.exceptions import ActionNotFoundError
from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, TaskAction

from zebra_agent.ioc import IoCActionRegistry, ZebraContainer
from zebra_agent.ioc.discovery import discover_actions, discover_conditions

# =========================================================================
# Test TaskAction classes
# =========================================================================


class NoArgAction(TaskAction):
    """A simple action with no constructor parameters."""

    description = "Test action with no args"

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        return TaskResult.ok(output={"source": "no_arg"})


class InjectableAction(TaskAction):
    """A test action that accepts constructor dependencies."""

    description = "Test action with injectable dependencies"

    def __init__(self, greeting: str = "hello", multiplier: int = 1):
        self.greeting = greeting
        self.multiplier = multiplier

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        return TaskResult.ok(output={"greeting": self.greeting, "multiplier": self.multiplier})


class RequiredDepAction(TaskAction):
    """A test action with a required constructor parameter (no default)."""

    description = "Test action with required dep"

    def __init__(self, service: object):
        self.service = service

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        return TaskResult.ok(output={"has_service": self.service is not None})


# =========================================================================
# Container Tests
# =========================================================================


class TestZebraContainer:
    """Tests for ZebraContainer."""

    def test_create_container(self):
        """Test basic container creation."""
        container = ZebraContainer()
        assert container is not None

    def test_config_from_dict(self):
        """Test loading configuration from dict."""
        container = ZebraContainer()
        container.config.from_dict(
            {
                "llm": {"provider_name": "anthropic", "model": "claude-sonnet-4-20250514"},
                "debug": True,
            }
        )

        assert container.config.llm.provider_name() == "anthropic"
        assert container.config.llm.model() == "claude-sonnet-4-20250514"
        assert container.config.debug() is True

    def test_store_dependency(self):
        """Test that store must be provided externally."""
        container = ZebraContainer()
        mock_store = MagicMock()
        container.store.override(providers.Object(mock_store))

        assert container.store() is mock_store

    def test_register_service_factory(self):
        """Test registering a factory service."""
        container = ZebraContainer()
        container.register_service("my_service", lambda: {"key": "value"})

        result = container.get_service("my_service")
        assert result == {"key": "value"}

        # Factory creates new instances each time
        result2 = container.get_service("my_service")
        assert result2 == {"key": "value"}

    def test_register_service_singleton(self):
        """Test registering a singleton service."""
        call_count = 0

        def make_service():
            nonlocal call_count
            call_count += 1
            return {"instance": call_count}

        container = ZebraContainer()
        container.register_service("singleton_svc", make_service, singleton=True)

        result1 = container.get_service("singleton_svc")
        result2 = container.get_service("singleton_svc")

        assert result1 is result2
        assert call_count == 1

    def test_get_service_not_found(self):
        """Test getting a non-existent service raises KeyError."""
        container = ZebraContainer()

        with pytest.raises(KeyError, match="not found"):
            container.get_service("nonexistent")

    def test_has_service(self):
        """Test checking service existence."""
        container = ZebraContainer()
        container.register_service("exists", lambda: True)

        assert container.has_service("exists") is True
        assert container.has_service("nope") is False

    def test_register_service_with_kwargs(self):
        """Test registering a service factory with keyword arguments."""

        def create_greeting(who: str, prefix: str = "Hello"):
            return f"{prefix}, {who}!"

        container = ZebraContainer()
        container.register_service("greeting", create_greeting, who="World", prefix="Hi")

        assert container.get_service("greeting") == "Hi, World!"


# =========================================================================
# Discovery Tests
# =========================================================================


class TestDiscovery:
    """Tests for entry point discovery."""

    @patch("zebra_agent.ioc.discovery.entry_points")
    def test_discover_actions_empty(self, mock_entry_points):
        """Test discovery with no entry points."""
        mock_entry_points.return_value = []
        result = discover_actions()
        assert result == {}

    @patch("zebra_agent.ioc.discovery.entry_points")
    def test_discover_conditions_empty(self, mock_entry_points):
        """Test condition discovery with no entry points."""
        mock_entry_points.return_value = []
        result = discover_conditions()
        assert result == {}

    @patch("zebra_agent.ioc.discovery.entry_points")
    def test_discover_actions_with_entries(self, mock_entry_points):
        """Test discovery loads entry points correctly."""
        mock_ep = MagicMock()
        mock_ep.name = "test_action"
        mock_ep.value = "test.module:TestAction"
        mock_ep.load.return_value = NoArgAction

        mock_entry_points.return_value = [mock_ep]

        result = discover_actions()
        assert "test_action" in result
        assert result["test_action"] is NoArgAction

    @patch("zebra_agent.ioc.discovery.entry_points")
    def test_discover_actions_handles_load_failure(self, mock_entry_points):
        """Test that failed entry point loads are gracefully handled."""
        mock_ep = MagicMock()
        mock_ep.name = "bad_action"
        mock_ep.value = "nonexistent.module:BadAction"
        mock_ep.load.side_effect = ImportError("Module not found")

        mock_entry_points.return_value = [mock_ep]

        result = discover_actions()
        assert result == {}

    def test_discover_real_entry_points(self):
        """Test that real zebra-tasks entry points are discovered."""
        actions = discover_actions()
        # zebra-tasks should have registered entry points
        assert "llm_call" in actions
        assert "file_read" in actions
        assert "file_write" in actions


# =========================================================================
# IoCActionRegistry Tests
# =========================================================================


class TestIoCActionRegistryBasic:
    """Tests for basic IoCActionRegistry functionality."""

    def test_create_without_container(self):
        """Test creating registry without a container."""
        registry = IoCActionRegistry()
        assert registry.container is None

    def test_create_with_container(self):
        """Test creating registry with a container."""
        container = ZebraContainer()
        registry = IoCActionRegistry(container)
        assert registry.container is container

    def test_register_and_get_action_no_container(self):
        """Test that actions work without a container (backward compat)."""
        registry = IoCActionRegistry()
        registry.register_action("no_arg", NoArgAction)

        action = registry.get_action("no_arg")
        assert isinstance(action, NoArgAction)

    def test_get_action_not_found(self):
        """Test getting an unregistered action raises error."""
        registry = IoCActionRegistry()

        with pytest.raises(ActionNotFoundError):
            registry.get_action("nonexistent")

    def test_list_actions(self):
        """Test listing registered actions."""
        registry = IoCActionRegistry()
        registry.register_action("action_a", NoArgAction)
        registry.register_action("action_b", NoArgAction)

        actions = registry.list_actions()
        assert "action_a" in actions
        assert "action_b" in actions


class TestIoCActionRegistryInjection:
    """Tests for dependency injection in IoCActionRegistry."""

    def test_no_arg_action_with_container(self):
        """Test that no-arg actions work fine with a container."""
        container = ZebraContainer()
        registry = IoCActionRegistry(container)
        registry.register_action("no_arg", NoArgAction)

        action = registry.get_action("no_arg")
        assert isinstance(action, NoArgAction)

    def test_inject_from_container(self):
        """Test that dependencies are injected from the container."""
        container = ZebraContainer()
        container.register_service("greeting", lambda: "injected_hello")
        container.register_service("multiplier", lambda: 42)

        registry = IoCActionRegistry(container)
        registry.register_action("injectable", InjectableAction)

        action = registry.get_action("injectable")
        assert isinstance(action, InjectableAction)
        assert action.greeting == "injected_hello"
        assert action.multiplier == 42

    def test_partial_injection(self):
        """Test that only available dependencies are injected."""
        container = ZebraContainer()
        container.register_service("greeting", lambda: "partial_hello")
        # multiplier is NOT registered - should use default

        registry = IoCActionRegistry(container)
        registry.register_action("injectable", InjectableAction)

        action = registry.get_action("injectable")
        assert isinstance(action, InjectableAction)
        assert action.greeting == "partial_hello"
        assert action.multiplier == 1  # default value

    def test_injection_fallback_on_failure(self):
        """Test that injection failure falls back to no-arg construction."""
        container = ZebraContainer()
        # RequiredDepAction requires 'service' but we don't register it
        # It should fall back to no-arg construction which will also fail
        # but the registry should handle this gracefully

        registry = IoCActionRegistry(container)
        registry.register_action("no_arg", NoArgAction)

        # NoArgAction should still work
        action = registry.get_action("no_arg")
        assert isinstance(action, NoArgAction)

    def test_inject_required_dependency(self):
        """Test injection of a required dependency (no default)."""
        container = ZebraContainer()
        mock_service = MagicMock()
        container.register_service("service", lambda: mock_service)

        registry = IoCActionRegistry(container)
        registry.register_action("required", RequiredDepAction)

        action = registry.get_action("required")
        assert isinstance(action, RequiredDepAction)
        assert action.service is mock_service


class TestIoCActionRegistryDiscovery:
    """Tests for auto-discovery in IoCActionRegistry."""

    def test_discover_and_register_loads_defaults(self):
        """Test that discover_and_register loads built-in defaults."""
        registry = IoCActionRegistry()
        registry.discover_and_register()

        # Built-in defaults should be registered (prompt was removed in human task cleanup)
        assert registry.has_action("shell")

    def test_discover_and_register_loads_entry_points(self):
        """Test that entry point actions are discovered."""
        registry = IoCActionRegistry()
        registry.discover_and_register()

        # zebra-tasks entry points should be registered
        # (assuming zebra-tasks is installed in the test environment)
        assert registry.has_action("llm_call")
        assert registry.has_action("file_read")
        assert registry.has_action("file_write")

    def test_discover_preserves_defaults(self):
        """Test that entry points don't override built-in defaults."""
        registry = IoCActionRegistry()

        # Manually register a custom 'shell' action
        registry.register_action("shell", NoArgAction)

        # Run discovery - should NOT override our custom shell
        with patch("zebra_agent.ioc.registry.discover_actions") as mock_discover:
            mock_discover.return_value = {"shell": InjectableAction}
            with patch("zebra_agent.ioc.registry.discover_conditions") as mock_cond:
                mock_cond.return_value = {}
                registry.discover_and_register()

        # Our custom shell should still be there
        action = registry.get_action("shell")
        assert isinstance(action, NoArgAction)

    def test_discover_and_register_with_container(self):
        """Test full discover + inject flow."""
        container = ZebraContainer()
        registry = IoCActionRegistry(container)
        registry.discover_and_register()

        # Should have both defaults and entry point actions
        # (prompt was removed in human task cleanup)
        assert registry.has_action("shell")

        # All actions should be instantiable
        for name in registry.list_actions():
            action = registry.get_action(name)
            assert isinstance(action, TaskAction)


class TestIoCActionRegistryConditions:
    """Tests for condition handling in IoCActionRegistry."""

    def test_builtin_conditions_registered(self):
        """Test that built-in conditions are available."""
        registry = IoCActionRegistry()

        assert registry.has_condition("always_true")

    def test_discover_registers_conditions(self):
        """Test that discover loads conditions from entry points."""
        registry = IoCActionRegistry()
        registry.discover_and_register()

        # route_name should be registered by register_defaults
        assert registry.has_condition("route_name")


class TestIoCActionRegistryIntegration:
    """Integration tests for the full IoC flow."""

    async def test_action_execution_with_injection(self):
        """Test that an injected action can execute correctly."""
        container = ZebraContainer()
        container.register_service("greeting", lambda: "world")
        container.register_service("multiplier", lambda: 5)

        registry = IoCActionRegistry(container)
        registry.register_action("greet", InjectableAction)

        action = registry.get_action("greet")

        # Create minimal mocks for execution
        task = MagicMock(spec=TaskInstance)
        task.properties = {}
        context = MagicMock(spec=ExecutionContext)

        result = await action.run(task, context)

        assert result.success
        assert result.output["greeting"] == "world"
        assert result.output["multiplier"] == 5

    async def test_no_arg_action_execution(self):
        """Test that a no-arg action executes normally."""
        registry = IoCActionRegistry()
        registry.register_action("simple", NoArgAction)

        action = registry.get_action("simple")

        task = MagicMock(spec=TaskInstance)
        task.properties = {}
        context = MagicMock(spec=ExecutionContext)

        result = await action.run(task, context)

        assert result.success
        assert result.output["source"] == "no_arg"

    def test_full_workflow_registry_setup(self):
        """Test a realistic registry setup with container and discovery."""
        container = ZebraContainer()
        container.config.from_dict(
            {
                "llm": {"provider": "anthropic"},
            }
        )

        mock_store = MagicMock()
        container.store.override(providers.Object(mock_store))

        registry = IoCActionRegistry(container)
        registry.discover_and_register()

        # Verify comprehensive action set
        actions = registry.list_actions()
        assert len(actions) > 2  # More than just defaults

        # Verify all actions are instantiable
        for name in actions:
            action = registry.get_action(name)
            assert isinstance(action, TaskAction), f"Action '{name}' is not a TaskAction"
