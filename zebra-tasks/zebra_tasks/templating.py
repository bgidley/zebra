"""Template helpers shared by task actions."""

from typing import Any

from zebra.tasks.base import ExecutionContext


def resolve_templates(value: Any, context: ExecutionContext) -> Any:
    """Resolve {{templates}} in every string inside a nested dict/list."""
    if isinstance(value, str):
        return context.resolve_template(value)
    if isinstance(value, dict):
        return {k: resolve_templates(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_templates(v, context) for v in value]
    return value
