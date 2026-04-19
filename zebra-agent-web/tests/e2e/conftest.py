import asyncio
import os
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure django is set up
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "zebra_agent_web.settings")
django.setup()

# We don't override django_db_setup here so that we use the standard test DB behavior
# (pytest-django will create a test database for us).

@pytest.fixture(scope="function")
def django_stores(db):
    """Initialize Django-backed stores for workflow engine and agent."""
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
        def __init__(self, store, memory, metrics):
            self.store = store
            self.memory = memory
            self.metrics = metrics

    return Stores(store, memory, metrics)

@pytest.fixture(scope="function")
def workflow_library(tmp_path, django_stores):
    from zebra_agent.library import WorkflowLibrary

    library_path = tmp_path / "workflows"
    library = WorkflowLibrary(library_path, django_stores.metrics)
    library.ensure_initialized()

    builtin_path = Path(__file__).parent.parent.parent.parent / "zebra-agent" / "workflows"
    if builtin_path.exists():
        library.copy_builtin_workflows(builtin_path)

    return library

@pytest.fixture(scope="function")
def workflow_engine(django_stores):
    from dependency_injector import providers
    from zebra.core.engine import WorkflowEngine
    from zebra_agent.ioc import IoCActionRegistry, ZebraContainer

    container = ZebraContainer()
    container.store.override(providers.Object(django_stores.store))

    registry = IoCActionRegistry(container)
    registry.discover_and_register()

    return WorkflowEngine(django_stores.store, registry)

@pytest.fixture(autouse=True)
def cassette_provider(request):
    """Patch the get_provider registry to use CassetteProvider."""
    import zebra_tasks.llm.providers
    import zebra_tasks.llm.providers.registry
    from zebra_tasks.llm._testing import CassetteProvider

    original_get_provider = zebra_tasks.llm.providers.registry.get_provider

    def mock_get_provider(name, model=None):
        base_provider = original_get_provider(name, model)
        
        # Build cassette path based on test name
        cassette_dir = Path(__file__).parent / "cassettes"
        cassette_name = f"{request.node.name}.json"
        
        # If running the 'test-nightly-oracle' job, we may want 'rewrite' or 'none' based on env.
        # By default, use 'once' (record if missing).
        record_mode = os.environ.get("VCR_RECORD_MODE", "once")
        
        return CassetteProvider(base_provider, cassette_path=cassette_dir / cassette_name, record_mode=record_mode)

    with patch("zebra_tasks.llm.providers.registry.get_provider", side_effect=mock_get_provider):
        with patch("zebra_tasks.llm.providers.get_provider", side_effect=mock_get_provider):
            yield

@pytest.fixture(scope="function")
def agent_loop(workflow_library, workflow_engine, django_stores, cassette_provider):
    """Create an AgentLoop configured with Django stores and Cassette LLM."""
    from zebra_agent.loop import AgentLoop

    # It will use the patched provider from `cassette_provider` fixture
    loop = AgentLoop(
        library=workflow_library,
        engine=workflow_engine,
        metrics=django_stores.metrics,
        memory=django_stores.memory,
        provider="anthropic",
        model=None,
    )

    return loop
