"""Zebra Agent - Self-improving agent library using zebra workflows.

This package provides:
- AgentLoop: Main agent loop for processing goals
- WorkflowLibrary: Workflow management and discovery
- Storage interfaces and implementations for memory and metrics
- IoC: Inversion of Control framework for task dependency injection

Storage backends:
- In-memory (default): Pure Python, no external dependencies
- Django ORM: Available via zebra-agent-web package

Example usage:
    from zebra_agent import AgentLoop, WorkflowLibrary
    from zebra_agent.ioc import ZebraContainer, IoCActionRegistry
    from zebra_agent.storage import InMemoryMemoryStore, InMemoryMetricsStore

    # Create in-memory storage
    memory = InMemoryMemoryStore()
    metrics = InMemoryMetricsStore()
    await memory.initialize()
    await metrics.initialize()

    # Create IoC registry with auto-discovery
    container = ZebraContainer()
    registry = IoCActionRegistry(container)
    registry.discover_and_register()

    # Create library and agent
    library = WorkflowLibrary(Path("~/.zebra/workflows"), metrics)
    agent = AgentLoop(library=library, engine=engine, metrics=metrics, memory=memory)
"""

__version__ = "0.1.0"

# Core classes
from zebra_agent.library import WorkflowInfo, WorkflowLibrary
from zebra_agent.loop import AgentLoop

# Data classes
from zebra_agent.memory import (
    AgentMemory,
    LongTermTheme,
    MemoryEntry,
    ShortTermSummary,
    estimate_tokens,
)
from zebra_agent.metrics import MetricsStore, TaskExecution, WorkflowRun, WorkflowStats

# IoC framework
from zebra_agent.ioc import IoCActionRegistry, ZebraContainer

# Storage interfaces and implementations
from zebra_agent.storage import (
    InMemoryMemoryStore,
    InMemoryMetricsStore,
    MemoryStore,
)
from zebra_agent.storage.interfaces import MetricsStore as MetricsStoreInterface

__all__ = [
    # Version
    "__version__",
    # Core classes
    "AgentLoop",
    "WorkflowLibrary",
    "WorkflowInfo",
    # IoC framework
    "ZebraContainer",
    "IoCActionRegistry",
    # Memory data classes
    "MemoryEntry",
    "ShortTermSummary",
    "LongTermTheme",
    "estimate_tokens",
    # Metrics data classes
    "WorkflowRun",
    "TaskExecution",
    "WorkflowStats",
    # Storage interfaces
    "MemoryStore",
    "MetricsStoreInterface",
    # Storage implementations (backward compatible aliases)
    "AgentMemory",  # Alias for InMemoryMemoryStore
    "MetricsStore",  # Alias for InMemoryMetricsStore
    # Storage implementations (explicit names)
    "InMemoryMemoryStore",
    "InMemoryMetricsStore",
]
