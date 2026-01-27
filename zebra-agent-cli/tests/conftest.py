"""Shared test fixtures for zebra-agent-cli.

These fixtures are duplicated from zebra-agent/tests/conftest.py because
pytest in a monorepo context requires each package's test directory to have
its own conftest when running tests individually.
"""

import os

import asyncpg
import pytest
from zebra_agent.memory import AgentMemory
from zebra_agent.metrics import MetricsStore

# Test database configuration
PG_HOST = os.environ.get("PGHOST", "/var/run/postgresql")
PG_PORT = int(os.environ.get("PGPORT", "5432"))
PG_DATABASE = os.environ.get("PGDATABASE", "opc")
PG_USER = os.environ.get("PGUSER", "opc")
PG_PASSWORD = os.environ.get("PGPASSWORD", None)


@pytest.fixture
async def cli_pg_pool():
    """Create a test database connection pool."""
    pool = await asyncpg.create_pool(
        host=PG_HOST,
        port=PG_PORT,
        database=PG_DATABASE,
        user=PG_USER,
        password=PG_PASSWORD,
    )
    yield pool
    await pool.close()


@pytest.fixture
async def metrics(cli_pg_pool):
    """Create MetricsStore with test configuration."""
    store = MetricsStore(
        host=PG_HOST,
        port=PG_PORT,
        database=PG_DATABASE,
        user=PG_USER,
        password=PG_PASSWORD,
    )
    await store.initialize()

    # Clean up before test
    await store._pool.execute("TRUNCATE TABLE workflow_runs")

    yield store

    # Clean up after test
    if store._pool:
        await store._pool.execute("TRUNCATE TABLE workflow_runs")
    await store.close()


@pytest.fixture
async def memory(cli_pg_pool):
    """Create AgentMemory with test configuration."""
    store = AgentMemory(
        host=PG_HOST,
        port=PG_PORT,
        database=PG_DATABASE,
        user=PG_USER,
        password=PG_PASSWORD,
        short_term_max_tokens=1000,  # Small limits for testing
        long_term_max_tokens=2000,
        compact_threshold=0.9,
    )
    await store.initialize()

    # Clean up before test
    await store._pool.execute("""
        TRUNCATE TABLE short_term_entries, short_term_summaries, 
                       long_term_themes, memory_state
    """)

    yield store

    # Clean up after test
    if store._pool:
        await store._pool.execute("""
            TRUNCATE TABLE short_term_entries, short_term_summaries, 
                           long_term_themes, memory_state
        """)
    await store.close()
