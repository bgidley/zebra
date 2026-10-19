"""OpenRouter: the one LLM backend (#205).

OpenRouter (https://openrouter.ai) serves models from many vendors behind one
OpenAI-compatible API. A tier (``low`` / ``medium`` / ``high`` / ``max``) is sent to
``openrouter/auto`` with that auto-router ``cost_tier``, so the router picks a model per
prompt within the price band; a ``vendor/model`` slug is sent as given. OpenRouter
reports each call's USD cost, which is what cost tracking records.

Set OPENROUTER_API_KEY. Optional: OPENROUTER_BASE_URL.
"""

import json
import os

from zebra_tasks.llm.base import (
    LLM_MAX_RETRIES,
    LLMProvider,
    LLMResponse,
    Message,
    MessageRole,
    TokenUsage,
    ToolCall,
    ToolDefinition,
    llm_request_timeout,
)
from zebra_tasks.llm.models import TIERS, normalize_model


class OpenRouterLLM(LLMProvider):
    """An LLM on OpenRouter: a tier through the auto router, or an exact model slug."""

    BASE_URL = "https://openrouter.ai/api/v1"
    AUTO_MODEL = "openrouter/auto"

    def __init__(self, model: str | None = None, api_key: str | None = None):
        import openai

        key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise ValueError("OpenRouter API key required. Set OPENROUTER_API_KEY.")
        self._model = normalize_model(model)
        self._client = openai.AsyncOpenAI(
            api_key=key,
            base_url=os.environ.get("OPENROUTER_BASE_URL", self.BASE_URL),
            default_headers={"X-Title": "Zebra"},
            timeout=llm_request_timeout(),
            max_retries=LLM_MAX_RETRIES,
        )

    @property
    def model(self) -> str:
        """The tier or ``vendor/model`` slug this LLM asks for."""
        return self._model

    def request_model(self) -> tuple[str, dict]:
        """The model id to send and any extra request body (the auto-router tier)."""
        if self._model in TIERS:
            plugin = {"id": "auto-router", "cost_tier": self._model}
            return self.AUTO_MODEL, {"plugins": [plugin]}
        return self._model, {}

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stop_sequences: list[str] | None = None,
    ) -> LLMResponse:
        """Generate a completion."""
        model, extra_body = self.request_model()
        kwargs: dict = {
            "model": model,
            "messages": [_to_openai(m) for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if extra_body:
            kwargs["extra_body"] = extra_body
        if stop_sequences:
            kwargs["stop"] = stop_sequences
        if tools:
            kwargs["tools"] = [_tool_to_openai(t) for t in tools]
            kwargs["tool_choice"] = "auto"
        return _from_openai(await self._client.chat.completions.create(**kwargs))


def _to_openai(msg: Message) -> dict:
    """A message in OpenAI chat format."""
    if msg.role == MessageRole.TOOL:
        return {"role": "tool", "tool_call_id": msg.tool_call_id, "content": msg.content}
    message: dict = {"role": msg.role.value, "content": msg.content}
    if msg.role == MessageRole.ASSISTANT and msg.tool_calls:
        message["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
            }
            for tc in msg.tool_calls
        ]
    return message


def _tool_to_openai(tool: ToolDefinition) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def _from_openai(response) -> LLMResponse:
    """An OpenAI-format response as an LLMResponse, with OpenRouter's reported cost."""
    choice = response.choices[0]
    message = choice.message
    tool_calls = None
    if message.tool_calls:
        tool_calls = []
        for tc in message.tool_calls:
            try:
                arguments = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                arguments = {}
            tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=arguments))
    cost = getattr(response.usage, "cost", None)
    return LLMResponse(
        content=message.content,
        tool_calls=tool_calls,
        finish_reason=choice.finish_reason,
        usage=TokenUsage(
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            cost_usd=float(cost) if cost is not None else 0.0,
        ),
        model=response.model,
        raw_response=response,
    )
