"""Structured JSON logging configuration via structlog.

Call ``configure_logging()`` once at Django settings load time.  All
existing ``logging.getLogger(...)`` calls automatically gain structured
output because structlog wraps the stdlib handler.

In DEBUG mode (local dev) human-readable console output is used instead.
"""

from __future__ import annotations

import logging

import structlog


def configure_logging(json_logs: bool = True) -> None:
    """Wire structlog into the stdlib root logger.

    Args:
        json_logs: If True (production), render each record as a JSON line.
                   If False (DEBUG), use the colourful dev console renderer.
    """
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    renderer = structlog.processors.JSONRenderer() if json_logs else structlog.dev.ConsoleRenderer()

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
