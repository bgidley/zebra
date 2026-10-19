"""The server's LLM provider is the fallback for every action (#204)."""

from types import SimpleNamespace

import pytest

from zebra_tasks.agent import reversibility
from zebra_tasks.llm.providers.registry import default_provider_name


def test_default_is_anthropic_without_setting(monkeypatch):
    monkeypatch.delenv("ZEBRA_LLM_PROVIDER", raising=False)
    assert default_provider_name() == "anthropic"


def test_default_follows_zebra_llm_provider(monkeypatch):
    monkeypatch.setenv("ZEBRA_LLM_PROVIDER", "openrouter")
    assert default_provider_name() == "openrouter"


@pytest.mark.parametrize(
    ("process_provider", "expected"),
    [(None, "openrouter"), ("kimi", "kimi")],
)
async def test_action_fallback_uses_server_provider(monkeypatch, process_provider, expected):
    """With no provider on the process, an action asks for the server's provider."""
    monkeypatch.setenv("ZEBRA_LLM_PROVIDER", "openrouter")
    asked: list[str] = []

    def fake_get_provider(name, model=None):
        asked.append(name)
        raise RuntimeError("stop here")

    monkeypatch.setattr(reversibility, "get_provider", fake_get_provider)
    props = {"__llm_provider_name__": process_provider} if process_provider else {}
    context = SimpleNamespace(process=SimpleNamespace(properties=props))

    assessment = await reversibility.assess_reversibility(
        "notify_email", "context_dependent", {}, "send a mail", context
    )

    assert asked == [expected]
    assert assessment.reversible is False  # fails closed when no provider
