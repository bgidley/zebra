"""Shared test fixtures for zebra-agent."""

import pytest

from zebra_agent.storage import InMemoryMemoryStore, InMemoryMetricsStore


@pytest.fixture
async def metrics():
    """Create an in-memory metrics store for testing."""
    store = InMemoryMetricsStore()
    await store.initialize()
    yield store
    await store.close()


@pytest.fixture
async def memory():
    """Create an in-memory memory store for testing.

    Uses small token limits for easier testing of compaction.
    """
    store = InMemoryMemoryStore(
        short_term_max_tokens=1000,  # Small limits for testing
        long_term_max_tokens=2000,
        compact_threshold=0.9,
    )
    await store.initialize()
    yield store
    await store.close()
