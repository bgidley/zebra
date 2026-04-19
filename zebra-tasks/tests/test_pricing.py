"""Tests for the pricing module."""

from zebra_tasks.llm.pricing import (
    ANTHROPIC_PRICING,
    DEFAULT_PRICING,
    calculate_cost,
    estimate_goal_cost,
    get_pricing,
)


class TestGetPricing:
    """Tests for get_pricing()."""

    def test_known_model(self):
        """Known model IDs return their pricing entry."""
        pricing = get_pricing("claude-sonnet-4-20250514")
        assert pricing["input"] == 3.00
        assert pricing["output"] == 15.00

    def test_haiku_pricing(self):
        """Haiku has lower pricing."""
        pricing = get_pricing("claude-haiku-4-20250414")
        assert pricing["input"] == 0.80
        assert pricing["output"] == 4.00

    def test_opus_pricing(self):
        """Opus has higher pricing."""
        pricing = get_pricing("claude-opus-4-20250514")
        assert pricing["input"] == 15.00
        assert pricing["output"] == 75.00

    def test_unknown_model_returns_default(self):
        """Unknown model falls back to DEFAULT_PRICING (sonnet-tier)."""
        pricing = get_pricing("claude-unknown-42")
        assert pricing == DEFAULT_PRICING

    def test_none_model_returns_default(self):
        """None model returns DEFAULT_PRICING."""
        pricing = get_pricing(None)
        assert pricing == DEFAULT_PRICING

    def test_all_pricing_entries_have_both_keys(self):
        """Every pricing entry has both input and output keys."""
        for model, pricing in ANTHROPIC_PRICING.items():
            assert "input" in pricing, f"Missing 'input' for {model}"
            assert "output" in pricing, f"Missing 'output' for {model}"
            assert pricing["input"] > 0, f"Non-positive input price for {model}"
            assert pricing["output"] > 0, f"Non-positive output price for {model}"


class TestCalculateCost:
    """Tests for calculate_cost()."""

    def test_zero_tokens(self):
        """Zero tokens costs zero."""
        assert calculate_cost("claude-sonnet-4-20250514", 0, 0) == 0.0

    def test_sonnet_cost(self):
        """Sonnet: 1000 input + 500 output tokens."""
        cost = calculate_cost("claude-sonnet-4-20250514", 1000, 500)
        # (1000 * 3.00 + 500 * 15.00) / 1_000_000
        expected = (3000 + 7500) / 1_000_000
        assert abs(cost - expected) < 1e-10

    def test_haiku_cost(self):
        """Haiku is cheapest."""
        cost = calculate_cost("claude-haiku-4-20250414", 10000, 5000)
        expected = (10000 * 0.80 + 5000 * 4.00) / 1_000_000
        assert abs(cost - expected) < 1e-10

    def test_opus_cost(self):
        """Opus is most expensive."""
        cost = calculate_cost("claude-opus-4-20250514", 10000, 5000)
        expected = (10000 * 15.00 + 5000 * 75.00) / 1_000_000
        assert abs(cost - expected) < 1e-10

    def test_none_model_uses_default(self):
        """None model uses default pricing."""
        cost = calculate_cost(None, 1000, 500)
        expected = (1000 * DEFAULT_PRICING["input"] + 500 * DEFAULT_PRICING["output"]) / 1_000_000
        assert abs(cost - expected) < 1e-10

    def test_large_token_counts(self):
        """Handles large token counts (1M+)."""
        cost = calculate_cost("claude-sonnet-4-20250514", 1_000_000, 500_000)
        expected = (1_000_000 * 3.00 + 500_000 * 15.00) / 1_000_000
        assert abs(cost - expected) < 1e-10


class TestEstimateGoalCost:
    """Tests for estimate_goal_cost()."""

    def test_zero_tokens(self):
        """Zero total tokens = zero cost."""
        assert estimate_goal_cost("claude-sonnet-4-20250514", 0) == 0.0

    def test_split_40_60(self):
        """Uses 40/60 input/output split."""
        cost = estimate_goal_cost("claude-sonnet-4-20250514", 10000)
        # 4000 input, 6000 output
        expected = calculate_cost("claude-sonnet-4-20250514", 4000, 6000)
        assert abs(cost - expected) < 1e-10

    def test_estimate_higher_than_pure_input(self):
        """Estimate should be higher than all-input (since output is pricier)."""
        all_input = calculate_cost("claude-sonnet-4-20250514", 10000, 0)
        estimated = estimate_goal_cost("claude-sonnet-4-20250514", 10000)
        assert estimated > all_input
