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

from zebra_agent.storage.interfaces import MemoryStore, MetricsStore, TrustStore
from zebra_agent.storage.memory import InMemoryMemoryStore
from zebra_agent.storage.metrics import InMemoryMetricsStore
from zebra_agent.storage.trust import (
    DEFAULT_DOMAINS,
    InMemoryTrustStore,
    TrustChangeRecord,
    TrustLevel,
    TrustSuggestion,
    list_domains,
    register_domain,
)

__all__ = [
    # Interfaces
    "MemoryStore",
    "MetricsStore",
    "TrustStore",
    # Implementations
    "InMemoryMemoryStore",
    "InMemoryMetricsStore",
    "InMemoryTrustStore",
    # Trust model
    "DEFAULT_DOMAINS",
    "TrustChangeRecord",
    "TrustLevel",
    "TrustSuggestion",
    "list_domains",
    "register_domain",
]
