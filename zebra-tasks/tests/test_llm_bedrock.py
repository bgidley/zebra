"""BedrockLLM on the Converse API, provider selection and token-priced cost (#335).

Bedrock is stubbed with botocore's ``Stubber``, which also checks every request
against the bedrock-runtime service model.
"""

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import boto3
import httpx
import pytest
from botocore import UNSIGNED
from botocore.exceptions import ReadTimeoutError
from botocore.stub import Stubber

from zebra_tasks.llm import bedrock
from zebra_tasks.llm.action import LLMCallAction
from zebra_tasks.llm.base import (
    LLM_MAX_RETRIES,
    LLMProviderAuthError,
    Message,
    ToolCall,
    ToolDefinition,
)
from zebra_tasks.llm.bedrock import (
    DEFAULT_TIER_MODELS,
    BedrockLLM,
    call_cost,
    get_client,
    make_client,
    parse_token_file,
    tier_model,
)
from zebra_tasks.llm.client import get_llm, set_llm_factory
from zebra_tasks.llm.models import normalize_model
from zebra_tasks.llm.openrouter import OpenRouterLLM
from zebra_tasks.notifications import owner

SONNET = DEFAULT_TIER_MODELS["medium"]


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for name in list(os.environ):
        if name.startswith(("ZEBRA_BEDROCK_", "ZEBRA_NOTIFY_", "ZEBRA_SMTP_")):
            monkeypatch.delenv(name)
    monkeypatch.setenv("ZEBRA_LLM_PROVIDER", "bedrock")
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIDTEST")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    bedrock.reset_clients()
    owner.reset_owner_notices()
    yield
    bedrock.reset_clients()
    owner.reset_owner_notices()


@pytest.fixture
def stubbed():
    client = boto3.client("bedrock-runtime", region_name="eu-west-1")
    with Stubber(client) as stub:
        yield client, stub
    stub.assert_no_pending_responses()


def _reply(content, stop="end_turn", tokens=(1000, 200)):
    return {
        "output": {"message": {"role": "assistant", "content": content}},
        "stopReason": stop,
        "usage": {
            "inputTokens": tokens[0],
            "outputTokens": tokens[1],
            "totalTokens": sum(tokens),
        },
        "metrics": {"latencyMs": 10},
    }


def _context(extras=None):
    store: dict = {}
    return SimpleNamespace(
        process=SimpleNamespace(id="proc-1", properties=store),
        extras=extras or {},
        get_process_property=lambda k, d=None: store.get(k, d),
        set_process_property=store.__setitem__,
    )


# --- text, JSON, tool use -----------------------------------------------------------


async def test_text_call_maps_system_messages_and_prices_tokens(stubbed):
    client, stub = stubbed
    stub.add_response(
        "converse",
        _reply([{"reasoningContent": {"reasoningText": {"text": "hm"}}}, {"text": "Paris"}]),
        {
            "modelId": SONNET,
            "system": [{"text": "Be brief."}],
            "messages": [{"role": "user", "content": [{"text": "Capital of France?"}]}],
            "inferenceConfig": {"maxTokens": 100 + BedrockLLM.REASONING_HEADROOM_TOKENS},
        },
    )
    llm = BedrockLLM("medium", client=client)

    response = await llm.complete(
        [Message.system("Be brief."), Message.user("Capital of France?")], max_tokens=100
    )

    assert response.content == "Paris"
    assert response.tool_calls is None
    assert response.finish_reason == "end_turn"
    assert response.model == SONNET
    assert (response.usage.input_tokens, response.usage.output_tokens) == (1000, 200)
    # Sonnet 5.5 list price: $2 / $10 per 1M tokens.
    assert response.usage.cost_usd == pytest.approx((1000 * 2 + 200 * 10) / 1_000_000)


async def test_older_model_gets_temperature_and_stop_sequences(stubbed):
    client, stub = stubbed
    model = "eu.anthropic.claude-sonnet-4-5-20250929-v1:0"
    stub.add_response(
        "converse",
        _reply([{"text": "ok"}]),
        {
            "modelId": model,
            "messages": [{"role": "user", "content": [{"text": "hi"}]}],
            "inferenceConfig": {
                "maxTokens": 10 + BedrockLLM.REASONING_HEADROOM_TOKENS,
                "temperature": 0.2,
                "stopSequences": ["END"],
            },
        },
    )
    llm = BedrockLLM(model, client=client)

    response = await llm.complete(
        [Message.user("hi")], temperature=0.2, max_tokens=10, stop_sequences=["END"]
    )

    assert response.model == model
    assert response.usage.cost_usd == pytest.approx((1000 * 3 + 200 * 15) / 1_000_000)


async def test_json_answer_is_plain_text(stubbed):
    client, stub = stubbed
    stub.add_response("converse", _reply([{"text": '```json\n{"a": 1}\n```'}]))
    from zebra_tasks.llm.structured import parse_llm_json

    response = await BedrockLLM("low", client=client).complete([Message.user("json please")])

    assert parse_llm_json(response.content) == {"a": 1}


async def test_tool_use_round_trip(stubbed):
    client, stub = stubbed
    tool = ToolDefinition(
        name="lookup",
        description="Look something up",
        parameters={"type": "object", "properties": {"q": {"type": "string"}}},
    )
    history = [
        Message.user("Find x"),
        Message.assistant("Looking", tool_calls=[ToolCall("t1", "lookup", {"q": "x"})]),
        Message.tool("x is 1", tool_call_id="t1", name="lookup"),
    ]
    stub.add_response(
        "converse",
        _reply(
            [{"toolUse": {"toolUseId": "t2", "name": "lookup", "input": {"q": "y"}}}],
            stop="tool_use",
        ),
        {
            "modelId": DEFAULT_TIER_MODELS["high"],
            "messages": [
                {"role": "user", "content": [{"text": "Find x"}]},
                {
                    "role": "assistant",
                    "content": [
                        {"text": "Looking"},
                        {"toolUse": {"toolUseId": "t1", "name": "lookup", "input": {"q": "x"}}},
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {"toolResult": {"toolUseId": "t1", "content": [{"text": "x is 1"}]}}
                    ],
                },
            ],
            "inferenceConfig": {"maxTokens": 4096 + BedrockLLM.REASONING_HEADROOM_TOKENS},
            "toolConfig": {
                "tools": [
                    {
                        "toolSpec": {
                            "name": "lookup",
                            "description": "Look something up",
                            "inputSchema": {"json": tool.parameters},
                        }
                    }
                ],
                "toolChoice": {"auto": {}},
            },
        },
    )

    response = await BedrockLLM("high", client=client).complete(history, tools=[tool])

    assert response.has_tool_calls
    assert response.tool_calls == [ToolCall(id="t2", name="lookup", arguments={"q": "y"})]
    assert response.finish_reason == "tool_use"
    assert response.content is None


def test_tool_history_without_tools_becomes_text():
    _, conversation = bedrock.to_converse(
        [
            Message.user("Find x"),
            Message.assistant("", tool_calls=[ToolCall("t1", "lookup", {"q": "x"})]),
            Message.tool("x is 1", tool_call_id="t1", name="lookup"),
            Message.tool("more", tool_call_id="t2", name="lookup"),
        ],
        with_tools=False,
    )
    blocks = [b for m in conversation for b in m["content"]]
    assert all(set(b) == {"text"} for b in blocks)
    # The two tool results merge into one user turn: roles alternate.
    assert [m["role"] for m in conversation] == ["user", "assistant", "user"]


# --- usage -> cost on the process and ledger ---------------------------------------


class FakeMetrics:
    def __init__(self):
        self.spend: list[dict] = []

    async def record_llm_spend(self, **kwargs):
        self.spend.append(kwargs)


async def test_recorded_cost_and_ledger_model_are_bedrock(stubbed, monkeypatch):
    client, stub = stubbed
    stub.add_response("converse", _reply([{"text": "ok"}], tokens=(2_000_000, 100_000)))
    monkeypatch.setattr(bedrock, "get_client", lambda region=None: client)
    metrics = FakeMetrics()
    context = _context({"__metrics_store__": metrics})

    await get_llm("low", context).complete([Message.user("hi")])

    haiku = DEFAULT_TIER_MODELS["low"]
    expected = 2 * 0.10 + 0.1 * 0.50
    assert context.process.properties["__total_cost__"] == pytest.approx(expected)
    assert context.process.properties["__token_history__"][0]["model"] == haiku
    assert metrics.spend[0]["model"] == haiku
    assert metrics.spend[0]["cost"] == pytest.approx(expected)


def test_price_override_and_unknown_model(monkeypatch, caplog):
    monkeypatch.setenv(
        "ZEBRA_BEDROCK_PRICES",
        json.dumps({"claude-sonnet-5-5": {"input": 3, "output": 30}, "nova-pro": [1, 2]}),
    )
    assert call_cost(SONNET, 1_000_000, 1_000_000) == pytest.approx(33)
    assert call_cost("amazon.nova-pro-v1:0", 1_000_000, 0) == pytest.approx(1)
    with caplog.at_level(logging.WARNING):
        # Unknown: the highest known rates, never free.
        assert call_cost("meta.llama9", 1_000_000, 0) == pytest.approx(15)
    assert "No Bedrock price" in caplog.text


def test_unreadable_price_override_is_ignored(monkeypatch):
    monkeypatch.setenv("ZEBRA_BEDROCK_PRICES", "not json")
    assert call_cost(SONNET, 1_000_000, 0) == pytest.approx(2)


# --- timeouts and retries -----------------------------------------------------------


def test_client_uses_llm_timeout_and_retries(monkeypatch):
    monkeypatch.setenv("ZEBRA_LLM_TIMEOUT_SECONDS", "42")
    config = make_client("eu-west-1", None).meta.config
    assert config.read_timeout == 42
    assert config.retries == {"total_max_attempts": LLM_MAX_RETRIES + 1, "mode": "standard"}


async def test_read_timeout_is_a_clear_timeout_error():
    class Slow:
        def converse(self, **kwargs):
            raise ReadTimeoutError(endpoint_url="https://bedrock")

    with pytest.raises(TimeoutError, match="timed out after 180s"):
        await BedrockLLM("medium", client=Slow()).complete([Message.user("hi")])


# --- expired credentials ------------------------------------------------------------


async def test_expired_token_raises_auth_error_and_notifies_once(stubbed, monkeypatch):
    client, stub = stubbed
    monkeypatch.setenv("AWS_PROFILE", "work")
    sent: list[tuple] = []

    async def fake_notify(key, subject, body):
        sent.append((key, subject, body))
        return ["webhook"]

    monkeypatch.setattr(owner, "notify_owner", fake_notify)
    for _ in range(2):
        stub.add_client_error(
            "converse",
            service_error_code="ExpiredTokenException",
            service_message="The security token included in the request is expired",
            http_status_code=403,
        )
    llm = BedrockLLM("medium", client=client)

    for _ in range(2):
        with pytest.raises(LLMProviderAuthError) as error:
            await llm.complete([Message.user("hi")])
    assert "AWS session expired — run `aws sso login --profile work`" in str(error.value)
    assert len(sent) == 2  # each failure asks; notify_owner itself rate-limits
    assert "aws sso login --profile work" in sent[0][2]


async def test_goal_task_fails_with_the_sso_message(stubbed, monkeypatch, mock_task, mock_context):
    client, stub = stubbed
    monkeypatch.setenv("ZEBRA_BEDROCK_SSO_PROFILE", "corp-dev")
    stub.add_client_error("converse", service_error_code="UnrecognizedClientException")
    monkeypatch.setattr(bedrock, "get_client", lambda region=None: client)

    async def quiet(*args):
        return []

    monkeypatch.setattr(owner, "notify_owner", quiet)
    mock_task.properties = {"prompt": "hi"}

    result = await LLMCallAction().run(mock_task, mock_context)

    assert result.success is False
    assert "run `aws sso login --profile corp-dev`" in result.error


async def test_notify_owner_posts_webhook_and_rate_limits(monkeypatch):
    posted: list[dict] = []

    def handler(request):
        posted.append(json.loads(request.content))
        return httpx.Response(204)

    real = httpx.AsyncClient
    monkeypatch.setattr(
        owner.httpx,
        "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
    )
    monkeypatch.setenv("ZEBRA_NOTIFY_WEBHOOK_URL", "https://hooks.example/x")

    assert await owner.notify_owner("k", "Subject", "Body") == ["webhook"]
    assert await owner.notify_owner("k", "Subject", "Body") == []
    assert posted == [{"subject": "Subject", "body": "Body"}]


async def test_notify_owner_without_channels_only_logs(caplog):
    with caplog.at_level(logging.ERROR):
        assert await owner.notify_owner("k2", "S", "B") == []
    assert "Owner notice: S: B" in caplog.text


# --- token file -------------------------------------------------------------------


def _write(path, text, mtime):
    path.write_text(text)
    os.utime(path, ns=(mtime, mtime))


def _bearer(client) -> str:
    request = SimpleNamespace(headers={})
    client.meta.events.emit("before-send.bedrock-runtime.Converse", request=request)
    return request.headers["Authorization"]


def test_token_file_bare_key_is_a_bearer_and_reloads_on_change(tmp_path, monkeypatch):
    path = tmp_path / "bedrock-token"
    monkeypatch.setenv("ZEBRA_BEDROCK_TOKEN_FILE", str(path))
    _write(path, "key-one\n", 1_000_000_000)

    first = get_client()
    assert first.meta.config.signature_version is UNSIGNED
    assert _bearer(first) == "Bearer key-one"
    assert get_client() is first  # unchanged file: cached

    _write(path, json.dumps({"token": "key-two"}), 2_000_000_000)
    second = get_client()
    assert second is not first
    assert _bearer(second) == "Bearer key-two"


def test_token_file_session_credentials(tmp_path, monkeypatch):
    path = tmp_path / "creds.json"
    later = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    path.write_text(
        json.dumps(
            {
                "Version": 1,
                "AccessKeyId": "ASIAFILE",
                "SecretAccessKey": "s3cret",
                "SessionToken": "sess",
                "Expiration": later,
            }
        )
    )
    monkeypatch.setenv("ZEBRA_BEDROCK_TOKEN_FILE", str(path))

    credentials = get_client()._request_signer._credentials
    assert (credentials.access_key, credentials.token) == ("ASIAFILE", "sess")


@pytest.mark.parametrize(
    "content",
    [
        json.dumps({"token": "k", "expires_at": "2020-01-01T00:00:00Z"}),
        json.dumps({"AccessKeyId": "A", "SecretAccessKey": "S", "Expiration": "2020-01-01T00:00Z"}),
        "",
        json.dumps({"nothing": 1}),
    ],
)
async def test_expired_or_bad_token_file_fails_before_calling(tmp_path, monkeypatch, content):
    path = tmp_path / "token"
    path.write_text(content)
    monkeypatch.setenv("ZEBRA_BEDROCK_TOKEN_FILE", str(path))
    monkeypatch.setattr(owner, "notify_owner", _no_notice)

    with pytest.raises(LLMProviderAuthError, match="AWS session expired"):
        await BedrockLLM("medium").complete([Message.user("hi")])


async def test_missing_token_file(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEBRA_BEDROCK_TOKEN_FILE", str(tmp_path / "absent"))
    monkeypatch.setattr(owner, "notify_owner", _no_notice)
    with pytest.raises(LLMProviderAuthError, match="is missing"):
        await BedrockLLM("medium").complete([Message.user("hi")])


async def _no_notice(*args):
    return []


def test_parse_token_file_formats():
    assert parse_token_file("  abc \n").token == "abc"
    parsed = parse_token_file('{"token": "t", "expires_at": "2099-01-01T00:00:00+00:00"}')
    assert parsed.token == "t" and not parsed.expired


# --- tiers, provider selection, model names --------------------------------------


def test_tier_map_defaults_and_overrides(monkeypatch):
    assert tier_model("low") == "global.anthropic.claude-haiku-5-5"
    assert tier_model("max") == "global.anthropic.claude-opus-5-5"
    monkeypatch.setenv("ZEBRA_BEDROCK_MODEL_MEDIUM", "eu.anthropic.claude-sonnet-5-5")
    assert BedrockLLM("medium").model_id() == "eu.anthropic.claude-sonnet-5-5"
    assert BedrockLLM("medium").model == "medium"


def test_provider_selection(monkeypatch):
    assert isinstance(get_llm("low"), BedrockLLM)
    monkeypatch.setenv("ZEBRA_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    assert isinstance(get_llm("low"), OpenRouterLLM)
    monkeypatch.delenv("ZEBRA_LLM_PROVIDER")
    assert isinstance(get_llm("low"), OpenRouterLLM)


def test_llm_factory_still_wins_on_bedrock():
    fake = object()
    set_llm_factory(lambda model: fake)
    assert get_llm("low") is fake


def test_normalize_model_on_bedrock(caplog):
    assert normalize_model("global.anthropic.claude-opus-5-5") == "global.anthropic.claude-opus-5-5"
    assert normalize_model("amazon.nova-pro-v1:0") == "amazon.nova-pro-v1:0"
    arn = "arn:aws:bedrock:eu-west-1:123456789012:inference-profile/MyProfile"
    assert normalize_model(arn) == arn
    assert normalize_model("high") == "high"
    with caplog.at_level(logging.WARNING):
        assert normalize_model("anthropic/claude-opus-5") == "high"
        assert normalize_model("moonshotai/kimi-k3") == "low"
        assert normalize_model("openai/gpt-9") == "medium"
    assert "OpenRouter model" in caplog.text


def test_normalize_model_on_openrouter_is_unchanged(monkeypatch):
    monkeypatch.setenv("ZEBRA_LLM_PROVIDER", "openrouter")
    assert normalize_model("moonshotai/kimi-k3") == "moonshotai/kimi-k3"
    # A Bedrock ID from a workflow made at work reads as its tier at home.
    assert normalize_model("global.anthropic.claude-sonnet-5-5") == "medium"


def test_unknown_provider_falls_back_to_openrouter(monkeypatch, caplog):
    monkeypatch.setenv("ZEBRA_LLM_PROVIDER", "vertex")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    with caplog.at_level(logging.ERROR):
        assert isinstance(get_llm("low"), OpenRouterLLM)
    assert "Unknown ZEBRA_LLM_PROVIDER" in caplog.text


async def test_throttling_is_a_normal_error_not_an_auth_error(stubbed):
    client, stub = stubbed
    stub.add_client_error(
        "converse", service_error_code="ThrottlingException", http_status_code=429
    )
    from botocore.exceptions import ClientError

    with pytest.raises(ClientError) as error:
        await BedrockLLM("medium", client=client).complete([Message.user("hi")])
    assert not isinstance(error.value, LLMProviderAuthError)
    assert not bedrock.is_auth_error(error.value)
