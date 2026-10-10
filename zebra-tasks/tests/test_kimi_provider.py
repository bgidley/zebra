"""Tests for KimiProvider: live model aliases and fixed-temperature requests (#164)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from zebra_tasks.llm.base import Message
from zebra_tasks.llm.models import KIMI_MODELS
from zebra_tasks.llm.providers.kimi import KimiProvider

THINKING_OFF = {"thinking": {"type": "disabled"}}


def _response():
    message = MagicMock(content='{"ok": true}', tool_calls=None)
    usage = MagicMock(prompt_tokens=10, completion_tokens=5)
    return MagicMock(choices=[MagicMock(message=message, finish_reason="stop")], usage=usage)


def _provider(model=None):
    provider = KimiProvider(model=model, api_key="test-key")
    provider._client = MagicMock()
    provider._client.chat.completions.create = AsyncMock(return_value=_response())
    return provider


@pytest.mark.parametrize(
    "alias, model",
    [
        (None, "kimi-k2.6"),
        ("kimi", "kimi-k2.6"),
        ("kimi-32k", "kimi-k2.6"),  # retired moonshot-v1 aliases keep working
        ("kimi-auto", "kimi-k2.6"),
        ("kimi-k3", "kimi-k3"),
        ("kimi-code", "kimi-k2.7-code-highspeed"),
        ("kimi-k2.7-code", "kimi-k2.7-code"),  # raw ids pass through
        # Anthropic tier names used across workflows map to Kimi tiers
        ("haiku", "kimi-k2.6"),
        ("sonnet", "kimi-k2.6"),
        ("opus", "kimi-k3"),
        # other providers' ids fall back to the default
        ("claude-haiku-4-5-20251001", "kimi-k2.6"),
        ("gpt-4o", "kimi-k2.6"),
        ("", "kimi-k2.6"),
    ],
)
def test_aliases_resolve_to_live_models(alias, model):
    assert _provider(alias)._model == model


def test_no_alias_points_at_retired_moonshot_v1():
    assert not [v for v in KIMI_MODELS.values() if v.startswith("moonshot-v1")]
    assert KimiProvider.DEFAULT_MODEL in KimiProvider.CONTEXT_WINDOWS


def test_context_windows():
    assert _provider("kimi")._model == "kimi-k2.6"
    assert _provider("kimi").max_context_tokens == 262144
    assert _provider("kimi-k3").max_context_tokens == 1048576


async def test_complete_sends_no_temperature_and_disables_thinking():
    provider = _provider("kimi")

    response = await provider.complete([Message.user("hi")], temperature=0.3, max_tokens=500)

    kwargs = provider._client.chat.completions.create.call_args.kwargs
    assert "temperature" not in kwargs
    assert kwargs["extra_body"] == THINKING_OFF
    assert kwargs["model"] == "kimi-k2.6"
    assert kwargs["max_tokens"] == 500
    assert response.content == '{"ok": true}'


async def test_thinking_only_model_gets_neither_temperature_nor_thinking():
    provider = _provider("kimi-code")

    await provider.complete([Message.user("hi")], temperature=0.3)

    kwargs = provider._client.chat.completions.create.call_args.kwargs
    assert "temperature" not in kwargs
    assert "extra_body" not in kwargs


async def test_stream_uses_same_sampling_rules():
    provider = _provider("kimi-k3")

    async def _empty():
        return
        yield  # pragma: no cover

    provider._client.chat.completions.create = AsyncMock(return_value=_empty())
    _ = [chunk async for chunk in provider.stream([Message.user("hi")], temperature=0.2)]

    kwargs = provider._client.chat.completions.create.call_args.kwargs
    assert kwargs["stream"] is True
    assert "temperature" not in kwargs
    assert kwargs["extra_body"] == THINKING_OFF


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("KIMI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="Kimi API key required"):
        KimiProvider()
