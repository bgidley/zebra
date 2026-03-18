"""ASGI config for zebra-agent-web project.

It exposes the ASGI callable as a module-level variable named ``application``.

The budget daemon is automatically started as a background asyncio task on
the first incoming HTTP or WebSocket request (unless disabled via the
``DAEMON_AUTO_START`` setting).
"""

import asyncio
import logging
import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "zebra_agent_web.settings")

# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models.
django_asgi_app = get_asgi_application()

# Import routing after Django setup
from zebra_agent_web.api.routing import websocket_urlpatterns

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Budget daemon auto-start middleware
# ---------------------------------------------------------------------------

_daemon_task: asyncio.Task | None = None
_daemon_stop: asyncio.Event | None = None


def _should_auto_start() -> bool:
    """Check if daemon auto-start is enabled in settings."""
    from django.conf import settings

    agent_settings = getattr(settings, "ZEBRA_AGENT_SETTINGS", {})
    return agent_settings.get("DAEMON_AUTO_START", True)


async def _start_daemon_if_needed() -> None:
    """Spawn the daemon as a background task (once only)."""
    global _daemon_task, _daemon_stop

    if _daemon_task is not None:
        return  # already started

    if not _should_auto_start():
        return

    from zebra_agent_web.api.daemon import run_daemon_loop

    _daemon_stop = asyncio.Event()
    _daemon_task = asyncio.create_task(_guarded_daemon_loop(_daemon_stop), name="budget-daemon")
    logger.info("Budget daemon auto-started as background task.")


async def _guarded_daemon_loop(stop_event: asyncio.Event) -> None:
    """Wrapper that catches CancelledError for clean shutdown."""
    from zebra_agent_web.api.daemon import run_daemon_loop

    try:
        await run_daemon_loop(stop_event)
    except asyncio.CancelledError:
        logger.info("Budget daemon task cancelled (server shutting down).")
    except Exception:
        logger.exception("Budget daemon crashed unexpectedly.")


class DaemonStarterMiddleware:
    """Thin ASGI middleware that auto-starts the budget daemon.

    On the first HTTP or WebSocket connection the daemon loop is spawned
    via ``asyncio.create_task``.  Subsequent requests are a no-op.

    This approach works with Daphne (which does not support ASGI lifespan
    events) and avoids running the daemon during management commands like
    ``migrate`` or ``shell``.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            await _start_daemon_if_needed()
        return await self.app(scope, receive, send)


_inner_app = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": URLRouter(websocket_urlpatterns),
    }
)

application = DaemonStarterMiddleware(_inner_app)
