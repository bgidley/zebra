"""AWS Bedrock: the LLM provider when ``ZEBRA_LLM_PROVIDER=bedrock`` (#335).

Calls go to the Bedrock **Converse** API (``bedrock-runtime``, boto3 run in a worker
thread). A tier maps to a model or inference profile (``ZEBRA_BEDROCK_MODEL_LOW`` /
``_MEDIUM`` / ``_HIGH`` / ``_MAX``); an exact Bedrock ID is sent as given. Bedrock
reports tokens, not dollars, so each call is priced from a per-model table
(``ZEBRA_BEDROCK_PRICES`` overrides it) and the budget and cost caps work as on
OpenRouter.

Settings:
    AWS_REGION / AWS_DEFAULT_REGION: Bedrock region (default ``us-east-1``).
    ZEBRA_BEDROCK_TOKEN_FILE: a credentials file written by the host (WZ6, #340), re-read
        whenever it changes. Without it the standard boto3 chain is used (``AWS_PROFILE``,
        env keys, SSO, instance role).
    ZEBRA_BEDROCK_SSO_PROFILE: the profile named in the "run aws sso login" message
        (default ``AWS_PROFILE``).

Token file formats (see ``specs/work-zebra-mac-design.md``):
    - a bare Bedrock API key (the whole file, stripped)
    - JSON ``{"token": "<api key>", "expires_at": "<ISO-8601>"}`` (``expires_at`` optional)
    - JSON in the ``credential_process`` shape that
      ``aws configure export-credentials --format process`` prints:
      ``{"Version": 1, "AccessKeyId": …, "SecretAccessKey": …, "SessionToken": …,
      "Expiration": "<ISO-8601>"}``

Missing or expired credentials raise ``LLMProviderAuthError`` with what to run, and the
owner is notified (``zebra_tasks.notifications.owner``).
"""

import asyncio
import json
import logging
import os
import re
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from zebra_tasks.llm.base import (
    LLM_MAX_RETRIES,
    LLMProvider,
    LLMProviderAuthError,
    LLMResponse,
    Message,
    MessageRole,
    TokenUsage,
    ToolCall,
    ToolDefinition,
    llm_request_timeout,
)
from zebra_tasks.llm.models import TIERS, normalize_model

logger = logging.getLogger(__name__)

DEFAULT_REGION = "us-east-1"
TOKEN_FILE_ENV = "ZEBRA_BEDROCK_TOKEN_FILE"
PRICES_ENV = "ZEBRA_BEDROCK_PRICES"
CONNECT_TIMEOUT_SECONDS = 10

#: Default model per tier: Anthropic global cross-region inference profiles.
#: Override with ``ZEBRA_BEDROCK_MODEL_<TIER>`` where the account enables others.
DEFAULT_TIER_MODELS: dict[str, str] = {
    "low": "global.anthropic.claude-haiku-5-5",
    "medium": "global.anthropic.claude-sonnet-5-5",
    "high": "global.anthropic.claude-opus-5-5",
    "max": "global.anthropic.claude-opus-5-5",
}

#: USD per 1M (input, output) tokens, matched against the model ID (longest key first).
#: Anthropic list prices; regional (non-global) Bedrock profiles can cost a little more,
#: so set ``ZEBRA_BEDROCK_PRICES`` to the account's actual rates.
DEFAULT_PRICES: dict[str, tuple[float, float]] = {
    "claude-fable-5-2": (8.0, 40.0),
    "claude-fable-5": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-opus-4-5": (5.0, 25.0),
    "claude-opus-4": (15.0, 75.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-4": (3.0, 15.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-haiku-4-5": (1.0, 5.0),
}

# Models that refuse sampling parameters (temperature) with a 400.
_NO_SAMPLING = re.compile(
    r"claude-(?:fable|mythos|opus-5|sonnet-5|haiku-5|opus-4-[78])", re.IGNORECASE
)

# Error codes that mean the credentials are missing, expired or wrong.
_AUTH_ERROR_CODES = {
    "ExpiredToken",
    "ExpiredTokenException",
    "UnrecognizedClientException",
    "InvalidSignatureException",
    "InvalidClientTokenId",
    "UnauthorizedException",
}
_AUTH_WORDS = re.compile(r"expired|token|authenticat|credential", re.IGNORECASE)


def tier_model(tier: str) -> str:
    """The Bedrock model for *tier*: ``ZEBRA_BEDROCK_MODEL_<TIER>``, else the default."""
    return (
        os.environ.get(f"ZEBRA_BEDROCK_MODEL_{tier.upper()}", "").strip()
        or DEFAULT_TIER_MODELS[tier]
    )


def bedrock_region() -> str:
    return os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or DEFAULT_REGION


def price_table() -> dict[str, tuple[float, float]]:
    """Default prices with ``ZEBRA_BEDROCK_PRICES`` entries on top.

    The env var is JSON mapping a model ID (or a part of one) to
    ``{"input": usd_per_1m, "output": usd_per_1m}`` or ``[input, output]``.
    An unreadable value is logged and ignored.
    """
    table = dict(DEFAULT_PRICES)
    raw = os.environ.get(PRICES_ENV)
    if not raw:
        return table
    try:
        for key, value in json.loads(raw).items():
            if isinstance(value, dict):
                table[str(key).lower()] = (float(value["input"]), float(value["output"]))
            else:
                table[str(key).lower()] = (float(value[0]), float(value[1]))
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        logger.error("Ignoring unreadable %s", PRICES_ENV)
    return table


def call_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """USD cost of a call to *model_id*.

    A model the table does not know is priced at the table's highest rates, with a
    warning, so an unknown model never slips past the budget as free.
    """
    table = price_table()
    model = model_id.lower()
    for key in sorted(table, key=len, reverse=True):
        if key in model:
            per_in, per_out = table[key]
            break
    else:
        per_in = max(p[0] for p in table.values())
        per_out = max(p[1] for p in table.values())
        logger.warning("No Bedrock price for %r; charging the highest known rates", model_id)
    return (input_tokens * per_in + output_tokens * per_out) / 1_000_000


def sso_login_hint() -> str:
    profile = os.environ.get("ZEBRA_BEDROCK_SSO_PROFILE") or os.environ.get("AWS_PROFILE")
    return f"aws sso login --profile {profile or '<profile>'}"


def auth_error_message(detail: str) -> str:
    return f"AWS session expired — run `{sso_login_hint()}` ({detail})"


# --- credentials -----------------------------------------------------------------


@dataclass(frozen=True)
class FileCredentials:
    """What the token file holds: a bearer API key or session keys."""

    token: str | None = None
    access_key_id: str | None = None
    secret_access_key: str | None = None
    session_token: str | None = None
    expires_at: datetime | None = None

    @property
    def expired(self) -> bool:
        return self.expires_at is not None and self.expires_at <= datetime.now(UTC)


def parse_token_file(text: str) -> FileCredentials:
    """Parse a token file (formats in the module docstring); ``ValueError`` if unusable."""
    text = text.strip()
    if not text:
        raise ValueError("token file is empty")
    if not text.startswith("{"):
        return FileCredentials(token=text)
    data = json.loads(text)
    if data.get("AccessKeyId"):
        if not data.get("SecretAccessKey"):
            raise ValueError("token file has AccessKeyId but no SecretAccessKey")
        return FileCredentials(
            access_key_id=data["AccessKeyId"],
            secret_access_key=data["SecretAccessKey"],
            session_token=data.get("SessionToken"),
            expires_at=_parse_time(data.get("Expiration")),
        )
    if data.get("token"):
        return FileCredentials(token=data["token"], expires_at=_parse_time(data.get("expires_at")))
    raise ValueError("token file has neither 'token' nor 'AccessKeyId'")


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    when = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return when if when.tzinfo else when.replace(tzinfo=UTC)


_clients: dict[tuple, Any] = {}
_clients_lock = threading.Lock()


def reset_clients() -> None:
    """Drop cached boto3 clients (tests; after an auth failure)."""
    with _clients_lock:
        _clients.clear()


def _bearer_handler(token: str):
    def add_bearer(request, **_kwargs):
        request.headers["Authorization"] = f"Bearer {token}"

    return add_bearer


def make_client(region: str, credentials: FileCredentials | None):
    """A ``bedrock-runtime`` client for *credentials* (None: the boto3 chain)."""
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config

    options: dict[str, Any] = {
        "read_timeout": llm_request_timeout(),
        "connect_timeout": CONNECT_TIMEOUT_SECONDS,
        "retries": {"total_max_attempts": LLM_MAX_RETRIES + 1, "mode": "standard"},
    }
    if credentials is not None and credentials.token:
        # A Bedrock API key: no SigV4, an Authorization: Bearer header instead.
        session = boto3.Session()
        client = session.client(
            "bedrock-runtime",
            region_name=region,
            config=Config(signature_version=UNSIGNED, **options),
        )
        client.meta.events.register(
            "before-send.bedrock-runtime", _bearer_handler(credentials.token)
        )
        return client
    if credentials is not None:
        session = boto3.Session(
            aws_access_key_id=credentials.access_key_id,
            aws_secret_access_key=credentials.secret_access_key,
            aws_session_token=credentials.session_token,
        )
    else:
        session = boto3.Session()
    return session.client("bedrock-runtime", region_name=region, config=Config(**options))


def get_client(region: str | None = None):
    """The cached client for the current credentials, rebuilt when the token file changes.

    Raises ``LLMProviderAuthError`` when the token file is missing, unreadable or expired.
    """
    region = region or bedrock_region()
    path = os.environ.get(TOKEN_FILE_ENV)
    credentials: FileCredentials | None = None
    if path:
        try:
            mtime = os.stat(path).st_mtime_ns
        except OSError:
            raise LLMProviderAuthError(
                auth_error_message(f"Bedrock token file {path} is missing")
            ) from None
        key: tuple = (region, path, mtime)
        with _clients_lock:
            if key in _clients:
                client, credentials = _clients[key]
                if credentials.expired:
                    raise LLMProviderAuthError(
                        auth_error_message(f"Bedrock token in {path} expired")
                    )
                return client
        try:
            with open(path, encoding="utf-8") as f:
                credentials = parse_token_file(f.read())
        except (OSError, ValueError) as e:
            raise LLMProviderAuthError(
                auth_error_message(f"Bedrock token file {path} is unreadable: {e}")
            ) from None
        if credentials.expired:
            raise LLMProviderAuthError(auth_error_message(f"Bedrock token in {path} expired"))
    else:
        key = (region, None, None)
        with _clients_lock:
            if key in _clients:
                return _clients[key][0]
    client = make_client(region, credentials)
    with _clients_lock:
        # Only the newest version of a token file stays cached.
        for old in [k for k in _clients if k[:2] == key[:2]]:
            del _clients[old]
        _clients[key] = (client, credentials)
    return client


# --- the provider ----------------------------------------------------------------


class BedrockLLM(LLMProvider):
    """An LLM on AWS Bedrock (Converse API): a tier via the tier map, or an exact ID."""

    #: As on OpenRouter (#204): thinking models spend output tokens before answering.
    REASONING_HEADROOM_TOKENS = 4096

    def __init__(self, model: str | None = None, client: Any = None):
        self._model = normalize_model(model)
        self._client = client

    @property
    def model(self) -> str:
        """The tier or Bedrock ID this LLM asks for."""
        return self._model

    def model_id(self) -> str:
        """The Bedrock model / inference-profile ID requests are sent to."""
        return tier_model(self._model) if self._model in TIERS else self._model

    def request(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None,
        temperature: float,
        max_tokens: int,
        stop_sequences: list[str] | None,
    ) -> dict:
        """The Converse request body."""
        model_id = self.model_id()
        system, conversation = to_converse(messages, with_tools=bool(tools))
        inference: dict[str, Any] = {"maxTokens": max_tokens + self.REASONING_HEADROOM_TOKENS}
        if not _NO_SAMPLING.search(model_id):
            inference["temperature"] = temperature
        if stop_sequences:
            inference["stopSequences"] = stop_sequences
        body: dict[str, Any] = {
            "modelId": model_id,
            "messages": conversation,
            "inferenceConfig": inference,
        }
        if system:
            body["system"] = system
        if tools:
            body["toolConfig"] = {
                "tools": [_tool_to_converse(t) for t in tools],
                "toolChoice": {"auto": {}},
            }
        return body

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stop_sequences: list[str] | None = None,
    ) -> LLMResponse:
        """Generate a completion."""
        body = self.request(messages, tools, temperature, max_tokens, stop_sequences)
        try:
            response = await asyncio.to_thread(self._converse, body)
        except LLMProviderAuthError as e:
            await _notify_auth_failure(str(e))
            raise
        return from_converse(response, body["modelId"])

    def _converse(self, body: dict) -> dict:
        from botocore.exceptions import (
            ClientError,
            ConnectTimeoutError,
            CredentialRetrievalError,
            NoCredentialsError,
            ReadTimeoutError,
            SSOError,
            TokenRetrievalError,
        )

        client = self._client or get_client()
        try:
            return client.converse(**body)
        except (NoCredentialsError, CredentialRetrievalError, TokenRetrievalError, SSOError) as e:
            reset_clients()
            raise LLMProviderAuthError(auth_error_message(type(e).__name__)) from e
        except ClientError as e:
            if is_auth_error(e):
                reset_clients()
                code = e.response.get("Error", {}).get("Code", "")
                raise LLMProviderAuthError(auth_error_message(code or "unauthorised")) from e
            raise
        except (ReadTimeoutError, ConnectTimeoutError) as e:
            raise TimeoutError(
                f"Bedrock call timed out after {llm_request_timeout():.0f}s "
                f"({LLM_MAX_RETRIES} retries)"
            ) from e


def is_auth_error(error: Any) -> bool:
    """Whether a botocore ``ClientError`` means missing / expired / bad credentials."""
    response = getattr(error, "response", {}) or {}
    err = response.get("Error", {})
    code = err.get("Code", "")
    status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    if code in _AUTH_ERROR_CODES or status == 401:
        return True
    return code == "AccessDeniedException" and bool(_AUTH_WORDS.search(err.get("Message", "")))


async def _notify_auth_failure(message: str) -> None:
    from zebra_tasks.notifications.owner import notify_owner

    try:
        await notify_owner(
            "bedrock-auth",
            "Zebra: AWS session expired",
            f"{message}\n\nGoals that call the LLM fail until the session is renewed.",
        )
    except Exception:  # noqa: BLE001 - a notice must never mask the auth error
        logger.warning("Could not notify the owner of the Bedrock auth failure", exc_info=True)


# --- message mapping -------------------------------------------------------------


def to_converse(messages: list[Message], with_tools: bool = True) -> tuple[list, list]:
    """Messages as Converse ``system`` blocks and alternating user/assistant messages.

    Consecutive same-role messages (e.g. several tool results) are merged. Without
    *with_tools* (Converse refuses tool blocks when no ``toolConfig`` is sent), tool
    calls and results become text.
    """
    system: list[dict] = []
    conversation: list[dict] = []
    for msg in messages:
        if msg.role == MessageRole.SYSTEM:
            if msg.content:
                system.append({"text": msg.content})
            continue
        role, blocks = _message_blocks(msg, with_tools)
        if not blocks:
            blocks = [{"text": "(empty)"}]
        if conversation and conversation[-1]["role"] == role:
            conversation[-1]["content"].extend(blocks)
        else:
            conversation.append({"role": role, "content": blocks})
    if conversation and conversation[0]["role"] != "user":
        conversation.insert(0, {"role": "user", "content": [{"text": "(continue)"}]})
    return system, conversation


def _message_blocks(msg: Message, with_tools: bool) -> tuple[str, list[dict]]:
    if msg.role == MessageRole.TOOL:
        if not with_tools:
            label = msg.name or msg.tool_call_id
            return "user", [{"text": f"Tool result ({label}):\n{msg.content}"}]
        return "user", [
            {
                "toolResult": {
                    "toolUseId": msg.tool_call_id,
                    "content": [{"text": msg.content or "(empty)"}],
                }
            }
        ]
    blocks: list[dict] = [{"text": msg.content}] if msg.content else []
    if msg.role == MessageRole.ASSISTANT and msg.tool_calls:
        for tc in msg.tool_calls:
            if with_tools:
                blocks.append(
                    {"toolUse": {"toolUseId": tc.id, "name": tc.name, "input": tc.arguments}}
                )
            else:
                blocks.append({"text": f"Called tool {tc.name}: {json.dumps(tc.arguments)}"})
    return ("assistant" if msg.role == MessageRole.ASSISTANT else "user"), blocks


def _tool_to_converse(tool: ToolDefinition) -> dict:
    return {
        "toolSpec": {
            "name": tool.name,
            "description": tool.description,
            "inputSchema": {"json": tool.parameters},
        }
    }


def from_converse(response: dict, model_id: str) -> LLMResponse:
    """A Converse response as an LLMResponse, priced from its token usage."""
    content = response.get("output", {}).get("message", {}).get("content", [])
    texts: list[str] = []
    tool_calls: list[ToolCall] = []
    for block in content:
        if "text" in block:
            texts.append(block["text"])
        elif "toolUse" in block:
            use = block["toolUse"]
            arguments = use.get("input")
            tool_calls.append(
                ToolCall(
                    id=use["toolUseId"],
                    name=use["name"],
                    arguments=arguments if isinstance(arguments, dict) else {},
                )
            )
        # reasoningContent (thinking) is not part of the answer.
    usage = response.get("usage", {})
    input_tokens = int(usage.get("inputTokens", 0))
    output_tokens = int(usage.get("outputTokens", 0))
    return LLMResponse(
        content="".join(texts) if texts else None,
        tool_calls=tool_calls or None,
        finish_reason=response.get("stopReason", "end_turn"),
        usage=TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=call_cost(model_id, input_tokens, output_tokens),
        ),
        model=model_id,
        raw_response=response,
    )
