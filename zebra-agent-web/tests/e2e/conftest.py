import asyncio
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Ensure django is set up
import django
import pytest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "zebra_agent_web.settings")
django.setup()

# Worker threads per test for sync_to_async(thread_sensitive=False) store calls.
E2E_DB_THREADS = 4


@pytest.fixture(autouse=True)
async def _bounded_db_threads():
    """Bound and clean up the DB connections opened by store worker threads.

    Stores run ORM calls via ``sync_to_async(thread_sensitive=False)``, i.e. in
    the event loop's default executor, and each worker thread opens its own
    Django connection. pytest-asyncio gives every test a new loop, so without
    this every test leaked a pool of Oracle sessions — enough to hit the Always
    Free ADB's 30-session cap (shared with prod) and fail with DPY-4011 (#169).
    """
    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(max_workers=E2E_DB_THREADS, thread_name_prefix="e2e-db")
    loop.set_default_executor(executor)
    yield
    # Run one close on each worker: the barrier stops a thread taking two.
    barrier = threading.Barrier(E2E_DB_THREADS)

    def close_worker_connections() -> None:
        from django.db import connections

        connections.close_all()
        try:
            barrier.wait(timeout=10)
        except threading.BrokenBarrierError:
            pass

    await asyncio.gather(
        *(loop.run_in_executor(executor, close_worker_connections) for _ in range(E2E_DB_THREADS))
    )
    executor.shutdown(wait=True)


@pytest.fixture(scope="session")
def django_db_setup(django_test_environment, django_db_blocker):
    """Set up the test database.

    - Oracle (ORACLE_DSN set): use the pre-existing test schema directly;
      skip pytest-django's CREATE TABLESPACE (requires elevated privileges).
      The schema is kept up to date by `manage.py migrate` in CI before tests.
    - SQLite (no ORACLE_DSN): let pytest-django create a temporary test DB
      and run migrations automatically.
    """
    from django.db import connection

    if connection.vendor == "oracle":
        yield  # Oracle: schema already exists, use it directly
    else:
        from django.test.utils import setup_databases, teardown_databases

        with django_db_blocker.unblock():
            old_config = setup_databases(verbosity=0, interactive=False)
        yield
        with django_db_blocker.unblock():
            teardown_databases(old_config, verbosity=0)


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


@pytest.fixture(scope="function")
def agent_loop(workflow_library, workflow_engine, django_stores):
    """Create an AgentLoop that makes real LLM API calls.

    E2E tests must exercise the full stack including real LLM requests so
    that provider-level bugs (wrong kwargs, deprecated parameters, model changes)
    are caught before deployment.  Cassette replay is opt-in for local development
    via the CassetteProvider in zebra_tasks.llm._testing — it must never be the
    default in CI.
    """
    from zebra_agent.loop import AgentLoop

    loop = AgentLoop(
        library=workflow_library,
        engine=workflow_engine,
        metrics=django_stores.metrics,
        memory=django_stores.memory,
        provider=None,  # the server's provider (ZEBRA_LLM_PROVIDER)
        model=None,
    )

    return loop


@pytest.fixture
def test_user(db):
    """Create a test user for authentication."""
    from django.conf import settings
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = User.objects.create_user(username="testuser")

    # Avoid SQLite lock contention in SetupRedirectMiddleware during async tests
    settings._USERS_EXIST_CACHE = True

    return user


@pytest.fixture
def authenticated_async_client(async_client, test_user):
    """Return an async client authenticated as test_user."""
    async_client.force_login(test_user)
    return async_client
