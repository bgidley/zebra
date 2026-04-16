"""IoC-enabled ActionRegistry with dependency injection.

Extends the base ``ActionRegistry`` from zebra-py to support:
- Automatic discovery of task actions from Python entry points
- Constructor injection of dependencies from a ``ZebraContainer``
- Backward compatibility with existing no-arg TaskAction classes

The registry inspects each TaskAction's ``__init__`` signature and resolves
parameters from the container. Parameters with defaults are optional;
those without defaults are required but gracefully handled if missing.

Example:
    from zebra_agent.ioc import ZebraContainer, IoCActionRegistry

    container = ZebraContainer()
    container.config.from_dict({"llm": {"provider": "anthropic"}})

    registry = IoCActionRegistry(container)
    registry.discover_and_register()

    # Actions are now available with dependencies injected
    action = registry.get_action("llm_call")
"""

import inspect
import logging
from typing import Any, get_type_hints

from zebra.core.exceptions import ActionNotFoundError
from zebra.tasks.base import TaskAction
from zebra.tasks.registry import ActionRegistry

from zebra_agent.ioc.container import ZebraContainer
from zebra_agent.ioc.discovery import discover_actions, discover_conditions

logger = logging.getLogger(__name__)


class IoCActionRegistry(ActionRegistry):
    """ActionRegistry with IoC support for dependency injection.

    Extends the base ActionRegistry to:
    - Auto-discover actions and conditions from entry points
    - Inject constructor dependencies from a ZebraContainer
    - Fall back to no-arg construction when no container is provided
      or when a TaskAction has no constructor parameters

    The registry is a drop-in replacement for ``ActionRegistry`` and
    is fully backward compatible with existing code.
    """

    def __init__(self, container: ZebraContainer | None = None) -> None:
        """Initialize the IoC-enabled registry.

        Args:
            container: DI container for resolving dependencies. If None,
                falls back to no-arg construction (same as base ActionRegistry).
        """
        super().__init__()
        self._container = container

    @property
    def container(self) -> ZebraContainer | None:
        """The DI container used for dependency resolution."""
        return self._container

    def get_action(self, name: str) -> TaskAction:
        """Get a task action instance with dependencies injected.

        Inspects the action's ``__init__`` signature and resolves
        dependencies from the container. Falls back to no-arg
        construction if no container is configured or injection fails.

        Args:
            name: Registered action name.

        Returns:
            TaskAction instance with dependencies injected.

        Raises:
            ActionNotFoundError: If no action is registered with that name.
        """
        if name not in self._actions:
            raise ActionNotFoundError(f"No task action registered with name '{name}'")

        action_class = self._actions[name]

        if self._container is not None:
            return self._create_with_injection(action_class)

        return action_class()

    def _create_with_injection(self, action_class: type[TaskAction]) -> TaskAction:
        """Create an action instance with constructor injection.

        Inspects the ``__init__`` signature and resolves each parameter
        from the container. Parameters with defaults are optional.

        Args:
            action_class: TaskAction subclass to instantiate.

        Returns:
            Instantiated TaskAction with resolved dependencies.
        """
        init = action_class.__init__
        sig = inspect.signature(init)

        # Get type hints for better resolution
        try:
            hints = get_type_hints(init)
        except Exception:
            hints = {}

        resolved_kwargs: dict[str, Any] = {}

        for param_name, param in sig.parameters.items():
            # Skip self, *args, **kwargs
            if param_name == "self":
                continue
            if param.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ):
                continue

            resolved = self._resolve_dependency(param_name, hints.get(param_name))

            if resolved is not None:
                resolved_kwargs[param_name] = resolved
            elif param.default is inspect.Parameter.empty:
                logger.debug(
                    "Could not resolve required parameter '%s' for %s",
                    param_name,
                    action_class.__name__,
                )

        try:
            return action_class(**resolved_kwargs)
        except TypeError as e:
            logger.warning(
                "Dependency injection failed for %s: %s. Falling back to no-arg construction.",
                action_class.__name__,
                e,
            )
            return action_class()

    def _resolve_dependency(self, name: str, type_hint: type | None) -> Any:
        """Resolve a single dependency from the container.

        Resolution order:
        1. Direct match by parameter name in container providers
        2. Known name aliases (e.g. ``provider_factory`` -> ``llm_provider_factory``)

        Args:
            name: Parameter name from the ``__init__`` signature.
            type_hint: Optional type annotation for the parameter.

        Returns:
            Resolved dependency instance, or None if not found.
        """
        if self._container is None:
            return None

        # Try direct name match in container providers
        if self._container.has_service(name):
            try:
                return self._container.get_service(name)
            except Exception:
                logger.debug("Failed to resolve '%s' from container", name, exc_info=True)

        # Try known aliases
        _ALIASES: dict[str, str] = {
            "provider_factory": "llm_provider_factory",
            "llm_provider": "default_llm_provider",
        }
        alias = _ALIASES.get(name)
        if alias and self._container.has_service(alias):
            try:
                return self._container.get_service(alias)
            except Exception:
                logger.debug(
                    "Failed to resolve '%s' (alias '%s') from container",
                    name,
                    alias,
                    exc_info=True,
                )

        return None

    def discover_and_register(self) -> None:
        """Auto-discover and register actions from entry points.

        Performs the following in order:
        1. Snapshots any already-registered actions/conditions (to preserve them)
        2. Registers built-in defaults from zebra-py (shell, prompt, etc.)
        3. Discovers ``zebra.tasks`` entry points and registers them
        4. Discovers ``zebra.conditions`` entry points and registers them

        Pre-existing registrations and built-in defaults take priority
        over entry point discoveries when names collide.
        """
        # Snapshot pre-existing registrations so we don't override them
        pre_existing_actions = set(self._actions.keys())
        pre_existing_conditions = set(self._conditions.keys())

        # Register built-in defaults (won't override pre-existing)
        from zebra.tasks.actions import get_default_actions, get_default_conditions

        for name, action_class in get_default_actions().items():
            if name not in pre_existing_actions:
                self.register_action(name, action_class)

        for name, condition_class in get_default_conditions().items():
            if name not in pre_existing_conditions:
                self.register_condition(name, condition_class)

        # Discover task actions from entry points
        discovered_actions = discover_actions()
        for name, action_class in discovered_actions.items():
            if name not in self._actions:
                self.register_action(name, action_class)
                logger.debug("Registered action '%s' from entry point", name)
            else:
                logger.debug("Skipping action '%s' - already registered", name)

        # Discover conditions from entry points
        discovered_conditions = discover_conditions()
        for name, condition_class in discovered_conditions.items():
            if name not in self._conditions:
                self.register_condition(name, condition_class)
                logger.debug("Registered condition '%s' from entry point", name)

        logger.info(
            "IoCActionRegistry: %d actions, %d conditions registered",
            len(self._actions),
            len(self._conditions),
        )
