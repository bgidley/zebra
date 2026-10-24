"""Shared helpers for the data transform actions."""

from typing import Any

from zebra.core.models import TaskInstance
from zebra.tasks.base import ExecutionContext

from zebra_tasks.knowledge.extract import resolve_raw

MAX_INPUT_CHARS = 2_000_000


def input_value(task: TaskInstance, context: ExecutionContext) -> Any:
    """Resolve the ``data`` property, keeping structure for a pure ``{{template}}``.

    Raises:
        ValueError: ``data`` is missing, or is text longer than ``MAX_INPUT_CHARS``.
    """
    raw = task.properties.get("data")
    if raw is None:
        raise ValueError("'data' is required")
    value = resolve_raw(context, raw)
    if isinstance(value, str) and len(value) > MAX_INPUT_CHARS:
        raise ValueError(f"'data' is {len(value)} characters; the limit is {MAX_INPUT_CHARS}")
    return value


def input_text(task: TaskInstance, context: ExecutionContext) -> str:
    """Resolve ``data`` as non-empty text.

    Raises:
        ValueError: ``data`` is missing, too long, empty or not a string.
    """
    value = input_value(task, context)
    if not isinstance(value, str):
        raise ValueError(f"'data' must be text, got {type(value).__name__}")
    if not value.strip():
        raise ValueError("'data' is empty")
    return value
