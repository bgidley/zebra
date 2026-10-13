"""Hardcoded LLM pricing tables (Anthropic, Kimi) and cost calculation helpers.

Prices are in USD per 1 million tokens.  Update this file when a provider
publishes new pricing.
"""

from __future__ import annotations

# Mapping of model ID -> {"input": $/1M input tokens, "output": $/1M output tokens}
ANTHROPIC_PRICING: dict[str, dict[str, float]] = {
    # Current generation (Anthropic list prices, checked 2026-10-11)
    "claude-opus-5-5": {"input": 4.00, "output": 20.00},
    "claude-opus-4-8": {"input": 5.00, "output": 25.00},
    "claude-opus-4-7": {"input": 5.00, "output": 25.00},
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-haiku-5-5": {"input": 0.10, "output": 0.50},
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
    # Previous generation (still in CONTEXT_WINDOWS)
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
    "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
    "claude-3-sonnet-20240229": {"input": 3.00, "output": 15.00},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
}

# Kimi (Moonshot AI) list prices from https://platform.kimi.ai/docs/pricing/chat
# (checked 2026-10-10). Input is the cache-miss price: Zebra does not track cache hits,
# so this is the upper bound. Keys are the ids Kimi echoes in ``response.model``.
KIMI_PRICING: dict[str, dict[str, float]] = {
    "kimi-k3": {"input": 3.00, "output": 15.00},
    "kimi-k2.6": {"input": 0.95, "output": 4.00},
    "kimi-k2.7-code": {"input": 0.95, "output": 4.00},
    "kimi-k2.7-code-highspeed": {"input": 1.90, "output": 8.00},
}

PRICING: dict[str, dict[str, float]] = {**ANTHROPIC_PRICING, **KIMI_PRICING}

# Models billed at a higher rate for the whole call once its prompt exceeds a size:
# model ID -> (prompt-token threshold, pricing above it).
LONG_PROMPT_PRICING: dict[str, tuple[int, dict[str, float]]] = {
    "claude-haiku-5-5": (100_000, {"input": 0.50, "output": 2.50}),
}

# Fallback when the model ID is not in the table (sonnet-tier).
DEFAULT_PRICING: dict[str, float] = {"input": 3.00, "output": 15.00}


def get_pricing(model: str | None) -> dict[str, float]:
    """Return the pricing entry for *model*, falling back to DEFAULT_PRICING."""
    if model is None:
        return DEFAULT_PRICING
    return PRICING.get(model, DEFAULT_PRICING)


def calculate_cost(
    model: str | None,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Calculate the USD cost for a single LLM call.

    Applies LONG_PROMPT_PRICING when the call's prompt exceeds the model's threshold,
    so pass one call's usage, not totals summed across calls.

    Args:
        model: Model ID as returned by the provider (e.g. ``"claude-sonnet-5-5"``,
            ``"kimi-k2.6"``).
        input_tokens: Number of input (prompt) tokens.
        output_tokens: Number of output (completion) tokens.

    Returns:
        Cost in USD (float).
    """
    pricing = get_pricing(model)
    threshold, long_pricing = LONG_PROMPT_PRICING.get(model or "", (None, None))
    if threshold is not None and input_tokens > threshold:
        pricing = long_pricing
    return _cost(pricing, input_tokens, output_tokens)


def usage_cost(model: str | None, usage) -> float:
    """USD cost of one call: the provider-reported cost if any, else priced from the tables.

    Args:
        model: Model ID used for table pricing.
        usage: The call's ``TokenUsage``.
    """
    if getattr(usage, "cost_usd", None) is not None:
        return usage.cost_usd
    return calculate_cost(model, usage.input_tokens, usage.output_tokens)


def _cost(pricing: dict[str, float], input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000


def estimate_goal_cost(
    model: str | None,
    estimated_total_tokens: int,
) -> float:
    """Rough cost estimate assuming a 40/60 input/output token split.

    Useful when you only know the total token count (e.g. from historical data)
    but not the input/output breakdown. Uses base rates: the total spans many calls,
    so long-prompt pricing is not applied.
    """
    input_tokens = int(estimated_total_tokens * 0.4)
    output_tokens = estimated_total_tokens - input_tokens
    return _cost(get_pricing(model), input_tokens, output_tokens)
