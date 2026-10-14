"""Template filters for formatting values in the web UI.

Usage in templates::

    {% load format_tags %}
    {{ run.cost|usd }}        -> $1,234.50, <$0.01, $0.00
    {{ step.duration_seconds|seconds }} -> 0.4s, 12s, 4m 05s, 1h 02m
    {{ value|pretty_json }}   -> strings as-is, anything else indented JSON
"""

import json
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django import template
from django.utils import timezone
from zebra.core.journal import TRUNCATED_KEY

register = template.Library()

_UNITS = (("d", 86400), ("h", 3600), ("m", 60))


@register.filter
def ago(value: datetime | None) -> str:
    """Compact relative time with one unit: ``now``, ``5m``, ``3h``, ``2d`` (then ``ago``).

    Args:
        value: An aware or naive datetime in the past.

    Returns:
        e.g. ``"3h ago"``; ``""`` for empty or invalid values.
    """
    if not isinstance(value, datetime):
        return ""
    now = timezone.now() if timezone.is_aware(value) else datetime.now()
    seconds = int((now - value).total_seconds())
    if seconds < 60:
        return "now"
    for suffix, size in _UNITS:
        if seconds >= size:
            return f"{seconds // size}{suffix} ago"
    return "now"


@register.filter
def usd(value: object) -> str:
    """Format a dollar amount with two decimals and a thousands separator.

    Amounts above zero but below one cent render as ``<$0.01`` so tiny LLM
    costs never read as free. Empty or unparseable values render as ``""``.

    Args:
        value: A number, Decimal or numeric string.

    Returns:
        The formatted amount, e.g. ``$1,234.50`` or ``-$3.20``.
    """
    if value is None or value == "":
        return ""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return ""
    if not amount.is_finite():
        return ""
    if Decimal(0) < amount < Decimal("0.01"):
        return "<$0.01"
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"


@register.filter
def seconds(value: object) -> str:
    """Format a duration in seconds compactly: ``0.4s``, ``12s``, ``4m 05s``, ``1h 02m``.

    Empty or unparseable values render as ``""``.
    """
    try:
        total = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return ""
    if total < 10:
        return f"{total:.1f}s"
    whole = int(total)
    if whole < 60:
        return f"{whole}s"
    if whole < 3600:
        return f"{whole // 60}m {whole % 60:02d}s"
    return f"{whole // 3600}h {(whole % 3600) // 60:02d}m"


@register.filter
def pretty_json(value: object) -> str:
    """Render a property value for display: strings unchanged, anything else as indented JSON.

    A value the step journal truncated (#184) renders as its preview with a size note.
    """
    if isinstance(value, dict) and value.get(TRUNCATED_KEY):
        return f"{value.get('preview', '')}\n... (truncated, {value.get('size', '?')} chars)"
    if isinstance(value, str):
        return value
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)
