"""Dependency injection container for Zebra Agent.

Provides a centralized container for managing services, configuration,
and factories used by task actions during workflow execution.

The container wraps the dependency-injector library's DeclarativeContainer
and adds convenience methods for service registration and lookup.

Example:
    container = ZebraContainer()
    container.config.from_dict({
        "llm": {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
    })

    # Provide a store
    from dependency_injector import providers
    from zebra.storage.memory import InMemoryStore
    store = InMemoryStore()
    container.store.override(providers.Object(store))

    # Register a custom service
    container.register_service("my_service", MyService, singleton=True)

    # The credential store is auto-registered as "credential_store" using the
    # KeyringCredentialStore backend (falls back to FileCredentialStore when
    # keyring is not available).  Override if needed:
    from zebra_agent.storage.credentials import FileCredentialStore
    container.register_service("credential_store", FileCredentialStore, singleton=True)
"""

import logging
from collections.abc import Callable
from typing import Any

from dependency_injector import containers, providers

logger = logging.getLogger(__name__)


class _ContainerDefinition(containers.DeclarativeContainer):
    """Internal declarative container definition.

    DeclarativeContainer uses a metaclass that creates DynamicContainer
    instances, so custom methods don't survive instantiation. We use
    this as the inner container and wrap it with ZebraContainer.
    """

    config = providers.Configuration()
    store = providers.Dependency()


class ZebraContainer:
    """Main DI container for Zebra Agent.

    Wraps a dependency-injector container and provides:
    - Configuration management via ``config`` provider
    - StateStore dependency (must be provided externally)
    - Dynamic service registration and lookup

    The container is passed to ``IoCActionRegistry`` which uses it to
    resolve constructor dependencies when instantiating TaskAction classes.
    """

    def __init__(self) -> None:
        self._container = _ContainerDefinition()
        self._register_default_credential_store()

    @property
    def config(self) -> providers.Configuration:
        """Access the configuration provider."""
        return self._container.config

    @property
    def store(self) -> providers.Dependency:
        """Access the store dependency provider."""
        return self._container.store

    @property
    def providers(self) -> dict[str, providers.Provider]:
        """Access all registered providers."""
        return self._container.providers

    def register_service(
        self,
        name: str,
        factory: Callable[..., Any],
        singleton: bool = False,
        **kwargs: Any,
    ) -> None:
        """Register a custom service on the container.

        Args:
            name: Service name for lookup during dependency injection.
            factory: Callable (class or function) that creates the service.
            singleton: If True, only one instance is created and reused.
            **kwargs: Additional keyword arguments passed to the factory.
        """
        if singleton:
            provider = providers.Singleton(factory, **kwargs)
        else:
            provider = providers.Factory(factory, **kwargs)

        self._container.set_provider(name, provider)
        logger.debug("Registered service '%s' (singleton=%s)", name, singleton)

    def get_service(self, name: str) -> Any:
        """Get a service instance by name.

        Args:
            name: Service name as registered.

        Returns:
            Service instance (created or cached depending on provider type).

        Raises:
            KeyError: If no service is registered with that name.
        """
        container_providers = self._container.providers
        if name not in container_providers:
            raise KeyError(f"Service '{name}' not found in container")
        return container_providers[name]()

    def has_service(self, name: str) -> bool:
        """Check if a service is registered.

        Args:
            name: Service name to check.

        Returns:
            True if the service exists in the container.
        """
        return name in self._container.providers

    def _register_default_credential_store(self) -> None:
        """Register a default CredentialStore under ``credential_store``.

        Attempts ``KeyringCredentialStore`` first; if the ``keyring`` package
        is not installed, falls back to ``FileCredentialStore``.  Callers can
        override by calling ``register_service("credential_store", ...)`` after
        construction.
        """
        try:
            import keyring  # noqa: F401

            from zebra_agent.storage.credentials import KeyringCredentialStore

            self.register_service("credential_store", KeyringCredentialStore, singleton=True)
            logger.debug("Default credential store: KeyringCredentialStore")
        except ImportError:
            from zebra_agent.storage.credentials import FileCredentialStore

            self.register_service("credential_store", FileCredentialStore, singleton=True)
            logger.debug("Default credential store: FileCredentialStore (keyring not available)")
