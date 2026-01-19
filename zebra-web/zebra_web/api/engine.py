"""Zebra workflow engine singleton for the web API.

Provides a shared WorkflowEngine instance that can be used across all views.
The engine is initialized when Django starts and uses PostgreSQL for storage.
"""

import asyncio
import logging
from typing import TYPE_CHECKING

from django.conf import settings

if TYPE_CHECKING:
    from zebra.core.engine import WorkflowEngine
    from zebra.storage.postgres import PostgreSQLStore

logger = logging.getLogger(__name__)

# Global instances
_store: "PostgreSQLStore | None" = None
_engine: "WorkflowEngine | None" = None
_initialized = False


def initialize():
    """Initialize the Zebra engine with PostgreSQL storage.

    Called once when Django starts (from ApiConfig.ready()).
    """
    global _initialized
    if _initialized:
        return

    logger.info("Zebra engine will be initialized on first request")
    _initialized = True


async def _async_init():
    """Async initialization of store and engine."""
    global _store, _engine

    if _store is not None:
        return

    # Import here to avoid issues at module load time
    from zebra.core.engine import WorkflowEngine
    from zebra.storage.postgres import PostgreSQLStore
    from zebra.tasks.registry import ActionRegistry

    zebra_settings = settings.ZEBRA_SETTINGS

    logger.info("Initializing PostgreSQL store...")
    _store = PostgreSQLStore(
        host=zebra_settings["POSTGRES_HOST"],
        port=zebra_settings["POSTGRES_PORT"],
        database=zebra_settings["POSTGRES_DATABASE"],
        user=zebra_settings["POSTGRES_USER"],
        password=zebra_settings["POSTGRES_PASSWORD"],
    )
    await _store.initialize()

    # Create action registry with defaults
    registry = ActionRegistry()
    registry.register_defaults()

    # Create engine
    _engine = WorkflowEngine(_store, registry)

    logger.info("Zebra engine initialized successfully")


def get_store() -> "PostgreSQLStore":
    """Get the PostgreSQL store instance.

    Raises:
        RuntimeError: If the store hasn't been initialized.
    """
    if _store is None:
        raise RuntimeError("Store not initialized. Call ensure_initialized() first.")
    return _store


def get_engine() -> "WorkflowEngine":
    """Get the WorkflowEngine instance.

    Raises:
        RuntimeError: If the engine hasn't been initialized.
    """
    if _engine is None:
        raise RuntimeError("Engine not initialized. Call ensure_initialized() first.")
    return _engine


async def ensure_initialized():
    """Ensure the engine is initialized (async).

    Call this at the start of any async view that needs the engine.
    """
    if _store is None:
        await _async_init()


def run_async(coro):
    """Run an async coroutine from sync code.

    This is used to bridge Django's sync views with our async Zebra code.
    For better performance, use async views directly.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop, create one
        return asyncio.run(coro)
    else:
        # There's a running loop, use it
        if loop.is_running():
            # We're in an async context, need to use a new thread
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        else:
            return loop.run_until_complete(coro)
