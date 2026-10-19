"""OpenRouterLLM: tiers through the auto router, exact slugs, reported cost (#205)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from zebra_tasks.llm.base import (
    DEFAULT_LLM_TIMEOUT_SECONDS,
    LLM_MAX_RETRIES,
    LLM_TIMEOUT_ENV,
    Message,
    ToolCall,
    ToolDefinition,
    llm_request_timeout,
)
from zebra_tasks.llm.openrouter import OpenRouterLLM


def _response(cost=None, tool_calls=None, model="deepseek/deepseek-v4.1-flash"):
    message = MagicMock(content="hi", tool_calls=tool_calls)
    usage = MagicMock(prompt_tokens=10, completion_tokens=5, cost=cost)
    return MagicMock(
        choices=[MagicMock(message=message, finish_reason="stop")], usage=usage, model=model
    )


def _llm(model=None, **response):
    llm = OpenRouterLLM(model=model, api_key="test-key")
    llm._client = MagicMock()
    llm._client.chat.completions.create = AsyncMock(return_value=_response(**response))
    return llm


def _sent(llm) -> dict:
    return llm._client.chat.completions.create.call_args.kwargs


@pytest.mark.parametrize("tier", ["low", "medium", "high", "max"])
async def test_tier_goes_to_the_auto_router_at_that_cost_tier(tier):
    llm = _llm(tier)

    await llm.complete([Message.user("hi")])

    assert _sent(llm)["model"] == "openrouter/auto"
    assert _sent(llm)["extra_body"] == {"plugins": [{"id": "auto-router", "cost_tier": tier}]}


async def test_slug_goes_to_that_model():
    llm = _llm("moonshotai/kimi-k3")

    await llm.complete([Message.user("hi")])

    assert _sent(llm)["model"] == "moonshotai/kimi-k3"
    assert "extra_body" not in _sent(llm)


@pytest.mark.parametrize(
    ("name", "model"),
    [(None, "medium"), ("haiku", "low"), ("claude-opus-5-5", "high"), ("HIGH", "high")],
)
def test_model_is_normalised(name, model):
    assert _llm(name).model == model


async def test_response_carries_reported_cost_and_model():
    response = await _llm("low", cost=0.0123).complete([Message.user("hi")], temperature=0.3)

    assert response.usage.cost_usd == 0.0123
    assert response.usage.input_tokens == 10
    assert response.model == "deepseek/deepseek-v4.1-flash"


async def test_no_reported_cost_is_zero():
    response = await _llm("low").complete([Message.user("hi")])
    assert response.usage.cost_usd == 0.0


async def test_messages_and_tools_in_openai_format():
    call = MagicMock(id="c1")
    call.function.name = "search"
    call.function.arguments = '{"q": "zebras"}'
    llm = _llm("medium", tool_calls=[call])
    tool = ToolDefinition(name="search", description="Search", parameters={"type": "object"})

    response = await llm.complete(
        [
            Message.system("be brief"),
            Message.user("find zebras"),
            Message.assistant("", tool_calls=[ToolCall(id="c0", name="search", arguments={})]),
            Message.tool("none found", tool_call_id="c0"),
        ],
        tools=[tool],
        stop_sequences=["END"],
    )

    sent = _sent(llm)
    assert [m["role"] for m in sent["messages"]] == ["system", "user", "assistant", "tool"]
    assert sent["messages"][2]["tool_calls"][0]["function"]["name"] == "search"
    assert sent["messages"][3] == {"role": "tool", "tool_call_id": "c0", "content": "none found"}
    assert sent["tools"][0]["function"]["name"] == "search"
    assert sent["tool_choice"] == "auto" and sent["stop"] == ["END"]
    assert response.tool_calls == [ToolCall(id="c1", name="search", arguments={"q": "zebras"})]


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        OpenRouterLLM()


def test_client_uses_bounded_timeout(monkeypatch):
    monkeypatch.setenv(LLM_TIMEOUT_ENV, "90")
    llm = OpenRouterLLM(api_key="test-key")
    assert llm._client.timeout == 90.0
    assert llm._client.max_retries == LLM_MAX_RETRIES


# Each API attempt is bounded well inside the goal budget (#183).


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
