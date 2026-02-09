"""Inversion of Control module for Zebra Agent.

Provides dependency injection capabilities for task actions using
the dependency-injector library and Python entry points for service discovery.

Main components:
- ZebraContainer: DI container for managing services and configuration
- IoCActionRegistry: Extended ActionRegistry with constructor injection
- discover_actions: Entry point discovery for task actions
- discover_conditions: Entry point discovery for routing conditions

Example:
    from zebra.core.engine import WorkflowEngine
    from zebra.storage.memory import InMemoryStore
    from zebra_agent.ioc import ZebraContainer, IoCActionRegistry

    # Create container with config
    container = ZebraContainer()
    container.config.from_dict({
        "llm": {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
    })

    # Create IoC registry - auto-discovers all actions from entry points
    registry = IoCActionRegistry(container)
    registry.discover_and_register()

    # Create engine with IoC registry
    store = InMemoryStore()
    engine = WorkflowEngine(store, registry)
"""

from zebra_agent.ioc.container import ZebraContainer
from zebra_agent.ioc.discovery import discover_actions, discover_conditions
from zebra_agent.ioc.registry import IoCActionRegistry

__all__ = [
    "ZebraContainer",
    "IoCActionRegistry",
    "discover_actions",
    "discover_conditions",
]
