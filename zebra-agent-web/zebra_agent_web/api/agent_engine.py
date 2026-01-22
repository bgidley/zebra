"""Zebra agent singleton for the web API.

Provides shared WorkflowLibrary, MetricsStore, and AgentLoop instances
that can be used across all agent views.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from django.conf import settings

if TYPE_CHECKING:
    from zebra_agent.library import WorkflowLibrary
    from zebra_agent.loop import AgentLoop
    from zebra_agent.metrics import MetricsStore

logger = logging.getLogger(__name__)

# Global instances
_library: "WorkflowLibrary | None" = None
_metrics: "MetricsStore | None" = None
_agent_loop: "AgentLoop | None" = None
_initialized = False


def _get_agent_settings() -> dict:
    """Get agent settings from Django settings or defaults."""
    return getattr(
        settings,
        "ZEBRA_AGENT_SETTINGS",
        {
            "LIBRARY_PATH": "~/.zebra/workflows",
            "METRICS_PATH": "~/.zebra/metrics.db",
            "LLM_PROVIDER": "anthropic",
            "LLM_MODEL": None,
        },
    )


def initialize() -> None:
    """Initialize the Zebra agent components.

    Called once when Django starts (from ApiConfig.ready()).
    """
    global _initialized
    if _initialized:
        return

    logger.info("Zebra agent will be initialized on first request")
    _initialized = True


async def _async_init() -> None:
    """Async initialization of agent components."""
    global _library, _metrics, _agent_loop

    if _library is not None:
        return

    # Import here to avoid issues at module load time
    from zebra_agent.library import WorkflowLibrary
    from zebra_agent.loop import AgentLoop
    from zebra_agent.metrics import MetricsStore

    from zebra_agent_web.api.engine import ensure_initialized as ensure_workflow_engine
    from zebra_agent_web.api.engine import get_engine

    agent_settings = _get_agent_settings()

    # Initialize metrics store
    metrics_path = Path(agent_settings["METRICS_PATH"]).expanduser()
    logger.info(f"Initializing metrics store at {metrics_path}")
    _metrics = MetricsStore(metrics_path)
    await _metrics._ensure_initialized()

    # Initialize workflow library
    library_path = Path(agent_settings["LIBRARY_PATH"]).expanduser()
    logger.info(f"Initializing workflow library at {library_path}")
    _library = WorkflowLibrary(library_path, _metrics)
    _library.ensure_initialized()

    # Copy built-in workflows if library is empty
    builtin_path = Path(__file__).parent.parent.parent.parent / "zebra-agent" / "workflows"
    if not builtin_path.exists():
        # Try alternate location (installed package)
        import zebra_agent

        builtin_path = Path(zebra_agent.__file__).parent.parent / "workflows"

    if builtin_path.exists():
        copied = _library.copy_builtin_workflows(builtin_path)
        if copied > 0:
            logger.info(f"Copied {copied} built-in workflows to library")

    # Ensure workflow engine is initialized
    await ensure_workflow_engine()
    engine = get_engine()

    # Initialize agent loop
    _agent_loop = AgentLoop(
        library=_library,
        engine=engine,
        metrics=_metrics,
        provider=agent_settings.get("LLM_PROVIDER", "anthropic"),
        model=agent_settings.get("LLM_MODEL"),
    )

    logger.info("Zebra agent initialized successfully")


def get_library() -> "WorkflowLibrary":
    """Get the WorkflowLibrary instance.

    Raises:
        RuntimeError: If the library hasn't been initialized.
    """
    if _library is None:
        raise RuntimeError("Library not initialized. Call ensure_initialized() first.")
    return _library


def get_metrics() -> "MetricsStore":
    """Get the MetricsStore instance.

    Raises:
        RuntimeError: If metrics hasn't been initialized.
    """
    if _metrics is None:
        raise RuntimeError("Metrics not initialized. Call ensure_initialized() first.")
    return _metrics


def get_agent_loop() -> "AgentLoop":
    """Get the AgentLoop instance.

    Raises:
        RuntimeError: If the agent loop hasn't been initialized.
    """
    if _agent_loop is None:
        raise RuntimeError("Agent loop not initialized. Call ensure_initialized() first.")
    return _agent_loop


async def ensure_initialized() -> None:
    """Ensure the agent is initialized (async).

    Call this at the start of any async view that needs the agent.
    """
    if _library is None:
        await _async_init()


def run_async(coro):
    """Run an async coroutine from sync code.

    This is used to bridge Django's sync views with our async agent code.
    For better performance, use async views directly.
    """
    import asyncio

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
