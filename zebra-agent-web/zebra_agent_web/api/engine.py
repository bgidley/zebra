"""Zebra workflow engine singleton for the agent web API.

Provides a shared WorkflowEngine instance that can be used across all views.
The engine is initialized when Django starts and uses Django ORM for storage.
"""

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zebra.core.engine import WorkflowEngine

    from zebra_agent_web.storage import DjangoStore

logger = logging.getLogger(__name__)

# Global instances
_store: "DjangoStore | None" = None
_engine: "WorkflowEngine | None" = None
_initialized = False


def initialize():
    """Initialize the Zebra engine with Django storage.

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
    from zebra.tasks.registry import ActionRegistry

    from zebra_agent_web.storage import DjangoStore

    logger.info("Initializing Django store...")
    _store = DjangoStore()
    await _store.initialize()

    # Create action registry with defaults
    registry = ActionRegistry()
    registry.register_defaults()

    # Register LLM actions from zebra-tasks
    try:
        from zebra_tasks.llm.action import LLMCallAction

        registry.register_action("llm_call", LLMCallAction)
        logger.info("Registered llm_call action from zebra-tasks")
    except ImportError:
        logger.warning("zebra-tasks not available, llm_call action not registered")

    # Register filesystem actions from zebra-tasks
    try:
        from zebra_tasks.filesystem import (
            DirectoryListAction,
            FileCopyAction,
            FileDeleteAction,
            FileExistsAction,
            FileInfoAction,
            FileMoveAction,
            FileReadAction,
            FileSearchAction,
            FileWriteAction,
        )

        registry.register_action("file_read", FileReadAction)
        registry.register_action("file_write", FileWriteAction)
        registry.register_action("file_copy", FileCopyAction)
        registry.register_action("file_move", FileMoveAction)
        registry.register_action("file_delete", FileDeleteAction)
        registry.register_action("file_search", FileSearchAction)
        registry.register_action("file_exists", FileExistsAction)
        registry.register_action("file_info", FileInfoAction)
        registry.register_action("directory_list", DirectoryListAction)
        logger.info("Registered 9 filesystem actions from zebra-tasks")
    except ImportError:
        logger.warning("zebra-tasks filesystem not available")

    # Create engine
    _engine = WorkflowEngine(_store, registry)

    logger.info("Zebra engine initialized successfully")


def get_store() -> "DjangoStore":
    """Get the DjangoStore instance.

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
