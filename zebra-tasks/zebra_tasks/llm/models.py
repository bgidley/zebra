"""LLM model tiers (#205) and the provider that serves them (#335).

Zebra asks for a *tier*, not a vendor model: ``low``, ``medium``, ``high`` or ``max``.
``ZEBRA_LLM_PROVIDER`` picks who serves it:

- ``openrouter`` (default): OpenRouter's auto router picks a model per prompt within the
  tier's price band. A ``vendor/model`` slug (e.g. ``moonshotai/kimi-k3``) names an exact
  OpenRouter model instead.
- ``bedrock``: AWS Bedrock, a tier mapped to a Bedrock model or inference profile
  (``ZEBRA_BEDROCK_MODEL_<TIER>``). An exact Bedrock ID (``global.anthropic.claude-…``
  or an ARN) names that model; an OpenRouter slug, say from a workflow synced from
  another Zebra, is read as its tier with a warning.
"""

import logging
import os
import re

logger = logging.getLogger(__name__)

#: Cost tiers, cheapest first. They are OpenRouter auto-router ``cost_tier`` values.
TIERS: tuple[str, ...] = ("low", "medium", "high", "max")

#: Tier used when a task, its process and the server name none.
DEFAULT_TIER = "medium"

#: Env var naming the LLM provider, and the providers it may name.
PROVIDER_ENV = "ZEBRA_LLM_PROVIDER"
PROVIDERS: tuple[str, ...] = ("openrouter", "bedrock")
DEFAULT_PROVIDER = "openrouter"

# Workflows, processes and settings stored before #205 name vendor models. Read them
# as the tier they stood for; nothing writes these names any more.
_LEGACY_TIERS = (
    (re.compile(r"haiku|kimi"), "low"),
    (re.compile(r"sonnet"), "medium"),
    (re.compile(r"opus"), "high"),
)

# A Bedrock model or inference-profile ID: optional geography prefix, then
# ``vendor.model`` (``global.anthropic.claude-sonnet-5-5``, ``amazon.nova-pro-v1:0``),
# or an ARN.
_BEDROCK_ID = re.compile(r"^(?:[a-z]{2,6}(?:-[a-z]+)?\.)?[a-z0-9]+\.[a-z0-9][a-z0-9.:-]*$")
_BEDROCK_ARN = re.compile(r"^arn:aws[a-z-]*:bedrock:", re.IGNORECASE)


def llm_provider() -> str:
    """The configured provider (``ZEBRA_LLM_PROVIDER``): ``openrouter`` or ``bedrock``."""
    raw = os.environ.get(PROVIDER_ENV, "").strip().lower()
    if not raw:
        return DEFAULT_PROVIDER
    if raw not in PROVIDERS:
        logger.error("Unknown %s=%r; using %s", PROVIDER_ENV, raw, DEFAULT_PROVIDER)
        return DEFAULT_PROVIDER
    return raw


def is_bedrock_model_id(name: str) -> bool:
    """Whether *name* is a Bedrock model / inference-profile ID or ARN."""
    name = name.strip()
    return bool(_BEDROCK_ARN.match(name) or _BEDROCK_ID.match(name.lower()))


def normalize_model(name: str | None) -> str:
    """Return the tier or exact model *name* stands for under the configured provider.

    ``None``, an empty string or an unknown name gives :data:`DEFAULT_TIER`.
    """
    model = (name or "").strip().lower()
    if not model:
        return DEFAULT_TIER
    if model in TIERS:
        return model
    if llm_provider() == "bedrock":
        if is_bedrock_model_id(model):
            return name.strip() if _BEDROCK_ARN.match(name.strip()) else model
        if "/" in model:
            tier = _legacy_tier(model) or DEFAULT_TIER
            logger.warning("OpenRouter model %r on Bedrock; using the %s tier", name, tier)
            return tier
    elif "/" in model:
        return model
    tier = _legacy_tier(model)
    if tier:
        return tier
    logger.warning("Unknown model %r; using the %s tier", name, DEFAULT_TIER)
    return DEFAULT_TIER


def _legacy_tier(model: str) -> str | None:
    for pattern, tier in _LEGACY_TIERS:
        if pattern.search(model):
            return tier
    return None
