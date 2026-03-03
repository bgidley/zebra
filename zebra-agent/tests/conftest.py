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
    """Create an in-memory memory store for testing."""
    store = InMemoryMemoryStore()
    await store.initialize()
    yield store
    await store.close()
