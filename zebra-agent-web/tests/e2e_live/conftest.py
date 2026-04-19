"""Pytest configuration for zebra-agent-web integration tests.

These tests run against the real Oracle database and make real LLM API calls.

Prerequisites:
- Oracle database configured in .env (ORACLE_DSN, ORACLE_USERNAME, ORACLE_PASSWORD)
- ANTHROPIC_API_KEY configured in .env
- Database migrations applied (python manage.py migrate)

Note: Environment variables are loaded automatically by pytest-dotenv plugin
(configured in root pyproject.toml with env_files = [".env"]).
"""

import asyncio
import os
from pathlib import Path

import pytest

# Set Django settings module before importing Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "zebra_agent_web.settings")

# Setup Django
import django

django.setup()


@pytest.fixture(scope="session")
def django_db_setup():
    """Skip test database creation - use the real database.

    This fixture overrides pytest-django's default behavior of creating
    a test database. We want to use the real Oracle database for integration tests.
    """
    pass


@pytest.fixture(scope="function")
def django_stores(db):
    """Initialize Django-backed stores for workflow engine and agent.

    The 'db' fixture from pytest-django enables database access for this test.

    Returns a simple container with all three stores:
    - store: DjangoStore for workflow engine state
    - memory: DjangoMemoryStore for agent memory
    - metrics: DjangoMetricsStore for workflow run tracking
    """
    from zebra_agent_web.memory_store import DjangoMemoryStore
    from zebra_agent_web.metrics_store import DjangoMetricsStore
    from zebra_agent_web.storage import DjangoStore

    store = DjangoStore()
    memory = DjangoMemoryStore()
    metrics = DjangoMetricsStore()

    # Initialize synchronously
    async def init_stores():
        await store.initialize()
        await memory.initialize()
        await metrics.initialize()

    asyncio.run(init_stores())

    class Stores:
        """Container for Django stores."""

        def __init__(self, store, memory, metrics):
            self.store = store
            self.memory = memory
            self.metrics = metrics

    return Stores(store, memory, metrics)


@pytest.fixture(scope="function")
def workflow_library(tmp_path, django_stores):
    """Create a workflow library with built-in workflows copied.

    Uses a temporary directory for the library path to avoid polluting
    the user's ~/.zebra/workflows directory during tests.
    """
    from zebra_agent.library import WorkflowLibrary

    library_path = tmp_path / "workflows"
    library = WorkflowLibrary(library_path, django_stores.metrics)
    library.ensure_initialized()

    # Copy built-in workflows from zebra-agent
    builtin_path = Path(__file__).parent.parent.parent / "zebra-agent" / "workflows"
    if builtin_path.exists():
        copied, _ = library.copy_builtin_workflows(builtin_path)
        print(f"Copied {copied} built-in workflows to test library at {library_path}")
    else:
        pytest.fail(f"Built-in workflows not found at {builtin_path}")

    return library


@pytest.fixture(scope="function")
def workflow_engine(django_stores):
    """Create a WorkflowEngine with Django storage and IoC registry.

    The registry auto-discovers all task actions from entry points,
    including the agent-specific actions (memory_check, workflow_selector, etc.).
    """
    from dependency_injector import providers
    from zebra.core.engine import WorkflowEngine
    from zebra_agent.ioc import IoCActionRegistry, ZebraContainer

    container = ZebraContainer()
    container.store.override(providers.Object(django_stores.store))

    registry = IoCActionRegistry(container)
    registry.discover_and_register()

    engine = WorkflowEngine(django_stores.store, registry)

    print(f"WorkflowEngine initialized with {len(registry.list_actions())} actions")

    return engine


@pytest.fixture(scope="function")
def agent_loop(workflow_library, workflow_engine, django_stores):
    """Create an AgentLoop configured with Django stores and real LLM.

    Uses Anthropic as the LLM provider (requires ANTHROPIC_API_KEY in env).
    """
    from zebra_agent.loop import AgentLoop

    loop = AgentLoop(
        library=workflow_library,
        engine=workflow_engine,
        metrics=django_stores.metrics,
        memory=django_stores.memory,
        provider="anthropic",
        model=None,  # Use default model
    )

    return loop
