"""LLM model tiers (#205).

Zebra asks for a *tier*, not a vendor model: ``low``, ``medium``, ``high`` or ``max``.
Every call goes through OpenRouter, whose auto router picks a model per prompt within
the tier's price band. A ``vendor/model`` slug (e.g. ``moonshotai/kimi-k3``) names an
exact OpenRouter model instead.
"""

import logging
import re

logger = logging.getLogger(__name__)

#: Cost tiers, cheapest first. They are OpenRouter auto-router ``cost_tier`` values.
TIERS: tuple[str, ...] = ("low", "medium", "high", "max")

#: Tier used when a task, its process and the server name none.
DEFAULT_TIER = "medium"

# Workflows, processes and settings stored before #205 name vendor models. Read them
# as the tier they stood for; nothing writes these names any more.
_LEGACY_TIERS = (
    (re.compile(r"haiku|kimi"), "low"),
    (re.compile(r"sonnet"), "medium"),
    (re.compile(r"opus"), "high"),
)


def normalize_model(name: str | None) -> str:
    """Return the tier or ``vendor/model`` slug *name* stands for.

    ``None``, an empty string or an unknown name gives :data:`DEFAULT_TIER`.
    """
    model = (name or "").strip().lower()
    if not model:
        return DEFAULT_TIER
    if model in TIERS or "/" in model:
        return model
    for pattern, tier in _LEGACY_TIERS:
        if pattern.search(model):
            return tier
    logger.warning("Unknown model %r; using the %s tier", name, DEFAULT_TIER)
    return DEFAULT_TIER
