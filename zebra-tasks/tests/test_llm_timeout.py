"""LLM providers bound each API attempt well inside the goal budget (#183).

The SDK default (600s per attempt, 2 retries) let one stalled request outlive a
600s goal. Every provider now uses ``llm_request_timeout()``.
"""

import pytest

from zebra_tasks.llm.base import (
    DEFAULT_LLM_TIMEOUT_SECONDS,
    LLM_MAX_RETRIES,
    LLM_TIMEOUT_ENV,
    llm_request_timeout,
)
from zebra_tasks.llm.providers.anthropic import AnthropicProvider
from zebra_tasks.llm.providers.kimi import KimiProvider
from zebra_tasks.llm.providers.openai import OpenAIProvider
from zebra_tasks.llm.providers.openrouter import OpenRouterProvider


def test_default_timeout_fits_three_attempts_in_a_600s_goal(monkeypatch):
    monkeypatch.delenv(LLM_TIMEOUT_ENV, raising=False)
    assert llm_request_timeout() == DEFAULT_LLM_TIMEOUT_SECONDS
    assert DEFAULT_LLM_TIMEOUT_SECONDS * (LLM_MAX_RETRIES + 1) < 600


def test_timeout_env_override(monkeypatch):
    monkeypatch.setenv(LLM_TIMEOUT_ENV, "45")
    assert llm_request_timeout() == 45.0


@pytest.mark.parametrize("raw", ["abc", "0", "-5"])
def test_invalid_timeout_env_falls_back_to_default(monkeypatch, raw):
    monkeypatch.setenv(LLM_TIMEOUT_ENV, raw)
    assert llm_request_timeout() == DEFAULT_LLM_TIMEOUT_SECONDS


@pytest.mark.parametrize(
    "make",
    [
        lambda: AnthropicProvider(api_key="test"),
        lambda: OpenAIProvider(api_key="test"),
        lambda: OpenRouterProvider(api_key="test"),
        lambda: KimiProvider(api_key="test"),
    ],
    ids=["anthropic", "openai", "openrouter", "kimi"],
)
def test_providers_use_bounded_timeout(monkeypatch, make):
    monkeypatch.setenv(LLM_TIMEOUT_ENV, "90")
    provider = make()
    assert provider._client.timeout == 90.0
    assert provider._client.max_retries == LLM_MAX_RETRIES
