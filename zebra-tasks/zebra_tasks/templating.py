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


def strip_templates(text: str) -> str:
    """Replace each ``{{…}}`` in ``text`` with a space; an unclosed ``{{`` is kept as is.

    Same result as substituting the lazy, DOTALL regex for ``{{…}}``, in linear time:
    that regex re-scans to the end from every unclosed ``{{``, which is quadratic on
    text with many opening braces and no close (#288).
    """
    parts: list[str] = []
    pos = 0
    while (start := text.find("{{", pos)) != -1:
        end = text.find("}}", start + 2)
        if end == -1:
            break
        parts.append(text[pos:start])
        parts.append(" ")
        pos = end + 2
    parts.append(text[pos:])
    return "".join(parts)
