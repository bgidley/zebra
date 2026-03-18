"""Hardcoded Anthropic pricing table and cost calculation helpers.

Prices are in USD per 1 million tokens.  Update this file when Anthropic
publishes new pricing.
"""

from __future__ import annotations

# Mapping of model ID -> {"input": $/1M input tokens, "output": $/1M output tokens}
ANTHROPIC_PRICING: dict[str, dict[str, float]] = {
    # Current generation
    "claude-haiku-4-20250414": {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-opus-4-20250514": {"input": 15.00, "output": 75.00},
    # Previous generation (still in CONTEXT_WINDOWS)
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
    "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
    "claude-3-sonnet-20240229": {"input": 3.00, "output": 15.00},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
}

# Fallback when the model ID is not in the table (sonnet-tier).
DEFAULT_PRICING: dict[str, float] = {"input": 3.00, "output": 15.00}


def get_pricing(model: str | None) -> dict[str, float]:
    """Return the pricing entry for *model*, falling back to DEFAULT_PRICING."""
    if model is None:
        return DEFAULT_PRICING
    return ANTHROPIC_PRICING.get(model, DEFAULT_PRICING)


def calculate_cost(
    model: str | None,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Calculate the USD cost for an LLM call.

    Args:
        model: Anthropic model ID (e.g. ``"claude-sonnet-4-20250514"``).
        input_tokens: Number of input (prompt) tokens.
        output_tokens: Number of output (completion) tokens.

    Returns:
        Cost in USD (float).
    """
    pricing = get_pricing(model)
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000


def estimate_goal_cost(
    model: str | None,
    estimated_total_tokens: int,
) -> float:
    """Rough cost estimate assuming a 40/60 input/output token split.

    Useful when you only know the total token count (e.g. from historical data)
    but not the input/output breakdown.
    """
    input_tokens = int(estimated_total_tokens * 0.4)
    output_tokens = estimated_total_tokens - input_tokens
    return calculate_cost(model, input_tokens, output_tokens)
