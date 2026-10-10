"""Template filters for formatting values in the web UI.

Usage in templates::

    {% load format_tags %}
    {{ run.cost|usd }}        -> $1,234.50, <$0.01, $0.00
"""

from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


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
