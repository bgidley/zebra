"""Template tag for rendering vendored Phosphor icons as inline SVG.

Usage in templates::

    {% load icon_tags %}
    {% icon "moon" class="h-5 w-5 text-gray-400" %}

Icons live in ``zebra_agent_web/icons/phosphor/<name>.svg`` (Phosphor
"regular" weight, MIT). Add a new icon by copying its SVG from
``@phosphor-icons/core`` into that directory.
"""

import logging
import re
from functools import cache
from pathlib import Path

from django import template
from django.utils.html import escape
from django.utils.safestring import SafeString, mark_safe

logger = logging.getLogger(__name__)

register = template.Library()

ICON_DIR = Path(__file__).resolve().parent.parent.parent / "icons" / "phosphor"

_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


@cache
def _load_svg(name: str) -> str | None:
    """Return the raw SVG markup for ``name``, or None if it is not vendored."""
    if not _NAME_RE.match(name):
        return None
    path = ICON_DIR / f"{name}.svg"
    if not path.is_file():
        return None
    return path.read_text().strip()


@register.simple_tag
def icon(name: str, **attrs: str) -> SafeString:
    """Render icon ``name`` as inline SVG.

    The SVG is ``aria-hidden`` and inherits colour from ``currentColor``. Any
    keyword arguments (``class``, ``title`` ...) become attributes on the
    ``<svg>`` element.

    Args:
        name: Phosphor icon name, e.g. ``"shield-check"``.
        **attrs: Extra attributes for the ``<svg>`` element.

    Returns:
        The SVG markup, or an empty string (with an error logged) when the icon
        is unknown so a typo never breaks a page.
    """
    svg = _load_svg(name)
    if svg is None:
        logger.error("Unknown icon %r (not in %s)", name, ICON_DIR)
        return mark_safe("")

    extra = {"aria-hidden": "true", "focusable": "false", **attrs}
    rendered = "".join(f' {escape(key)}="{escape(value)}"' for key, value in extra.items())
    return mark_safe(svg.replace("<svg", f"<svg{rendered}", 1))
