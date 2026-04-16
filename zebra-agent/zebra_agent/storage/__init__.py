"""Storage backends for the zebra-agent package.

This module provides abstract interfaces and implementations for agent storage:

Interfaces:
    - MemoryStore: Abstract interface for agent memory (short-term/long-term)
    - MetricsStore: Abstract interface for workflow metrics tracking

Implementations:
    - InMemoryMemoryStore: Pure Python in-memory memory storage
    - InMemoryMetricsStore: Pure Python in-memory metrics storage

Example usage:
    from zebra_agent.storage import InMemoryMemoryStore, InMemoryMetricsStore

    memory = InMemoryMemoryStore()
    await memory.initialize()

    metrics = InMemoryMetricsStore()
    await metrics.initialize()
"""

from zebra_agent.storage.interfaces import MemoryStore, MetricsStore
from zebra_agent.storage.memory import InMemoryMemoryStore
from zebra_agent.storage.metrics import InMemoryMetricsStore

__all__ = [
    # Interfaces
    "MemoryStore",
    "MetricsStore",
    # Implementations
    "InMemoryMemoryStore",
    "InMemoryMetricsStore",
]
