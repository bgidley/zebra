"""Available LLM model definitions and resolution helpers."""

# Mapping of friendly names to Anthropic API model IDs.
ANTHROPIC_MODELS: dict[str, str] = {
    "haiku": "claude-haiku-5-5",
    "sonnet": "claude-sonnet-5-5",
    "opus": "claude-opus-5-5",
}

# Kimi model aliases. Moonshot retired the moonshot-v1-* models (#164); the old
# aliases now map to kimi-k2.6 so existing settings keep working.
KIMI_MODELS: dict[str, str] = {
    "kimi": "kimi-k2.6",
    "kimi-k3": "kimi-k3",
    "kimi-code": "kimi-k2.7-code-highspeed",
    "kimi-8k": "kimi-k2.6",
    "kimi-32k": "kimi-k2.6",
    "kimi-128k": "kimi-k2.6",
    "kimi-auto": "kimi-k2.6",
}

# Anthropic tier names (used as "cheap / balanced / best" across workflows and actions)
# mapped to Kimi models, so `model: haiku` still works when the provider is kimi (#164).
KIMI_TIER_MODELS: dict[str, str] = {
    "haiku": "kimi-k2.6",
    "sonnet": "kimi-k2.6",
    "opus": "kimi-k3",
}

# Anthropic tier names mapped to OpenRouter slugs, so `model: haiku` still works when the
# provider is openrouter (#182).
OPENROUTER_TIER_MODELS: dict[str, str] = {
    "haiku": "anthropic/claude-haiku-5.5",
    "sonnet": "anthropic/claude-sonnet-5.5",
    "opus": "anthropic/claude-opus-5.5",
}

# With OPENROUTER_ROUTING=auto, tiers go to openrouter/auto at these auto-router cost tiers
# (low / medium / high / xhigh / max), so cheap steps stay cheap (#204).
OPENROUTER_AUTO_COST_TIERS: dict[str, str] = {
    "haiku": "low",
    "sonnet": "medium",
    "opus": "high",
}

# Ordered list of friendly names for UI dropdowns / API validation.
MODEL_CHOICES: list[str] = ["haiku", "sonnet", "opus"]

# Default friendly name when nothing is configured.
DEFAULT_MODEL_NAME: str = "sonnet"


def resolve_model_name(name: str | None) -> str | None:
    """Resolve a friendly name like ``"haiku"`` to the full API model ID.

    Returns ``None`` if *name* is ``None``.
    Passes through unrecognised names as-is (they may be full API IDs).
    """
    if name is None:
        return None
    return ANTHROPIC_MODELS.get(name.lower().strip(), name)


def friendly_model_name(api_model_id: str | None) -> str:
    """Reverse lookup: ``"claude-sonnet-4-20250514"`` → ``"sonnet"``.

    Returns the friendly name if found, otherwise returns the raw ID.
    Falls back to ``"sonnet"`` for ``None``.
    """
    if not api_model_id:
        return DEFAULT_MODEL_NAME
    for friendly, full_id in ANTHROPIC_MODELS.items():
        if full_id == api_model_id:
            return friendly
    # Not a known model — return as-is (could be a custom/future model)
    return api_model_id
