"""Tests for OpenRouterProvider: model resolution and provider-reported cost (#182)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from zebra_tasks.llm.action import LLMCallAction
from zebra_tasks.llm.base import Message, TokenUsage
from zebra_tasks.llm.pricing import calculate_cost, usage_cost
from zebra_tasks.llm.providers.openrouter import OpenRouterProvider
from zebra_tasks.llm.providers.registry import get_provider


def _response(cost=None):
    message = MagicMock(content="hi", tool_calls=None)
    usage = MagicMock(prompt_tokens=10, completion_tokens=5, cost=cost)
    return MagicMock(
        choices=[MagicMock(message=message, finish_reason="stop")],
        usage=usage,
        model="anthropic/claude-haiku-5.5",
    )


def _provider(model=None, cost=None):
    provider = OpenRouterProvider(model=model, api_key="test-key")
    provider._client = MagicMock()
    provider._client.chat.completions.create = AsyncMock(return_value=_response(cost))
    return provider


@pytest.mark.parametrize(
    "alias, model",
    [
        ("haiku", "anthropic/claude-haiku-5.5"),
        ("sonnet", "anthropic/claude-sonnet-5.5"),
        ("opus", "anthropic/claude-opus-5.5"),
        # Anthropic ids written for the anthropic provider keep their tier
        ("claude-haiku-5-5", "anthropic/claude-haiku-5.5"),
        # raw OpenRouter slugs pass through
        ("moonshotai/kimi-k3", "moonshotai/kimi-k3"),
        ("openrouter/auto", "openrouter/auto"),
        # anything else falls back to the default
        ("openrouter", "anthropic/claude-sonnet-5.5"),
        ("gpt-4o", "anthropic/claude-sonnet-5.5"),
        (None, "anthropic/claude-sonnet-5.5"),
    ],
)
def test_model_resolution(alias, model, monkeypatch):
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    monkeypatch.delenv("OPENROUTER_ROUTING", raising=False)
    assert _provider(alias)._model == model


def test_unknown_model_fallback_is_logged(caplog):
    _provider("gpt-4o")
    assert "OpenRouter has no model 'gpt-4o'" in caplog.text
    caplog.clear()
    _provider("openrouter")
    assert caplog.text == ""


def test_default_model_from_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", "google/gemma-4-31b-it")
    assert _provider("openrouter")._model == "google/gemma-4-31b-it"
    assert _provider("haiku")._model == "anthropic/claude-haiku-5.5"


@pytest.mark.parametrize(
    ("alias", "tier"),
    [
        ("haiku", "low"),
        ("sonnet", "medium"),
        ("opus", "high"),
        ("claude-haiku-5-5", "low"),
        ("openrouter", "medium"),
        (None, "medium"),
    ],
)
def test_auto_routing_maps_tiers_to_cost_tiers(alias, tier, monkeypatch):
    """OPENROUTER_ROUTING=auto: tiers go to openrouter/auto at a cost tier (#204)."""
    monkeypatch.setenv("OPENROUTER_ROUTING", "auto")
    provider = _provider(alias)
    assert provider._model == "openrouter/auto"
    assert provider._sampling_kwargs(0.7)["extra_body"] == {
        "plugins": [{"id": "auto-router", "cost_tier": tier}]
    }


def test_auto_routing_keeps_explicit_slugs(monkeypatch):
    monkeypatch.setenv("OPENROUTER_ROUTING", "auto")
    provider = _provider("moonshotai/kimi-k3")
    assert provider._model == "moonshotai/kimi-k3"
    assert "extra_body" not in provider._sampling_kwargs(0.7)


async def test_auto_routed_request_sends_the_plugin(monkeypatch):
    monkeypatch.setenv("OPENROUTER_ROUTING", "auto")
    provider = _provider("haiku")
    await provider.complete(messages=[Message.user("hi")])
    kwargs = provider._client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "openrouter/auto"
    assert kwargs["extra_body"]["plugins"][0]["cost_tier"] == "low"


def test_context_windows():
    assert _provider("opus").max_context_tokens == 1000000
    assert _provider("someone/unknown").max_context_tokens == 128000


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        OpenRouterProvider()


def test_registered_by_name(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    provider = get_provider("openrouter", "haiku")
    assert provider.name == "openrouter"
    assert provider.model == "anthropic/claude-haiku-5.5"


async def test_complete_carries_reported_cost():
    provider = _provider("haiku", cost=0.0123)

    response = await provider.complete([Message.user("hi")], temperature=0.3)

    kwargs = provider._client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "anthropic/claude-haiku-5.5"
    assert kwargs["temperature"] == 0.3
    assert response.usage.cost_usd == 0.0123
    assert response.usage.input_tokens == 10


async def test_complete_without_reported_cost():
    response = await _provider("haiku").complete([Message.user("hi")])
    assert response.usage.cost_usd is None


def test_usage_cost_prefers_reported_cost():
    assert usage_cost("claude-sonnet-5-5", TokenUsage(1000, 1000, cost_usd=0.5)) == 0.5
    assert usage_cost("claude-sonnet-5-5", TokenUsage(1000, 1000, cost_usd=0.0)) == 0.0
    assert usage_cost("claude-sonnet-5-5", TokenUsage(1000, 1000)) == calculate_cost(
        "claude-sonnet-5-5", 1000, 1000
    )


def test_llm_call_tracks_reported_cost():
    props: dict = {"__total_cost__": 1.0}
    context = MagicMock(extras={})
    context.get_process_property.side_effect = lambda k, d=None: props.get(k, d)
    context.set_process_property.side_effect = props.__setitem__

    LLMCallAction()._track_tokens(
        context, TokenUsage(10, 5, cost_usd=0.0123), model="anthropic/claude-haiku-5.5"
    )

    assert props["__total_cost__"] == pytest.approx(1.0123)
    assert props["__token_history__"][0]["cost"] == 0.0123


async def test_reasoning_headroom_added_to_max_tokens():
    """Reasoning would otherwise use a small budget up and leave an empty reply (#204)."""
    provider = _provider("low")
    await provider.complete([Message.user("hi")], max_tokens=500)
    sent = provider._client.chat.completions.create.call_args.kwargs
    assert sent["max_tokens"] == 500 + OpenRouterProvider.REASONING_HEADROOM_TOKENS
