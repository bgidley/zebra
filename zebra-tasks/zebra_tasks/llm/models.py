"""Available LLM model definitions and resolution helpers."""

# Mapping of friendly names to Anthropic API model IDs.
ANTHROPIC_MODELS: dict[str, str] = {
    "haiku": "claude-haiku-4-20250414",
    "sonnet": "claude-sonnet-4-20250514",
    "opus": "claude-opus-4-20250514",
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
