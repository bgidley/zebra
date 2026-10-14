"""Anthropic Claude LLM provider."""

import os
import re
from collections.abc import AsyncIterator

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


class AnthropicProvider(LLMProvider):
    """
    LLM provider for Anthropic Claude models.

    Requires the 'anthropic' package: pip install anthropic
    Set ANTHROPIC_API_KEY environment variable or pass api_key.
    """

    DEFAULT_MODEL = "claude-sonnet-5-5"

    # Model context windows (current Claude 4.x IDs)
    CONTEXT_WINDOWS = {
        "claude-opus-5-5": 1000000,
        "claude-sonnet-5-5": 1000000,
        "claude-haiku-5-5": 1000000,
        "claude-opus-4-8": 200000,
        "claude-sonnet-4-6": 200000,
        "claude-haiku-4-5-20251001": 200000,
        # Legacy IDs retained for graceful fallback
        "claude-opus-4-20250514": 200000,
        "claude-sonnet-4-20250514": 200000,
        "claude-3-5-sonnet-20241022": 200000,
        "claude-3-5-haiku-20241022": 200000,
        "claude-3-opus-20240229": 200000,
        "claude-3-haiku-20240307": 200000,
    }

    # Newer Claude 4+ models do not accept the `temperature` parameter — the API
    # returns a 400 invalid_request_error when it is included. Older Claude 3.x
    # models still accept it. This set lists models that reject the parameter;
    # every Claude 5-family model (claude-<tier>-5*) rejects it too.
    _NO_TEMPERATURE_MODELS = {
        "claude-opus-4-8",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
    }

    @classmethod
    def accepts_temperature(cls, model: str) -> bool:
        """Whether *model* accepts the ``temperature`` sampling parameter."""
        if model in cls._NO_TEMPERATURE_MODELS:
            return False
        return re.match(r"claude-[a-z]+-5", model) is None

    # At their default effort Sonnet 5.5 and Haiku 5.5 often skip thinking on short
    # prompts and reason aloud in the visible reply ("that's 5 words, need 3: ...").
    # At xhigh they think in a thinking block and return only the answer (#168).
    _XHIGH_EFFORT_PATTERN = re.compile(r"claude-(sonnet|haiku)-5")
    # Thinking counts against max_tokens, and callers size max_tokens for the answer
    # alone (often 150-600), so boosted-effort calls get this much on top. Unused
    # tokens are not billed.
    THINKING_HEADROOM_TOKENS = 4096

    @classmethod
    def effort_for(cls, model: str) -> str | None:
        """The ``output_config.effort`` to send for *model*, or None for the API default."""
        return "xhigh" if cls._XHIGH_EFFORT_PATTERN.match(model) else None

    def _apply_sampling(self, kwargs: dict, temperature: float) -> None:
        # Newer Claude 4+ models reject the temperature parameter with a 400
        if self.accepts_temperature(self._model):
            kwargs["temperature"] = temperature
        effort = self.effort_for(self._model)
        if effort:
            # extra_body: the pinned anthropic SDK predates the output_config argument
            kwargs["extra_body"] = {"output_config": {"effort": effort}}
            kwargs["max_tokens"] += self.THINKING_HEADROOM_TOKENS

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "anthropic package not installed. Install with: pip install anthropic"
            )

        from zebra_tasks.llm.models import resolve_model_name

        self._model = resolve_model_name(model) or self.DEFAULT_MODEL
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")

        if not self._api_key:
            raise ValueError("Anthropic API key required. Set ANTHROPIC_API_KEY or pass api_key.")

        self._client = anthropic.AsyncAnthropic(
            api_key=self._api_key,
            base_url=base_url,
            timeout=llm_request_timeout(),
            max_retries=LLM_MAX_RETRIES,
        )

    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def model(self) -> str:
        return self._model

    @property
    def max_context_tokens(self) -> int:
        return self.CONTEXT_WINDOWS.get(self._model, 200000)

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stop_sequences: list[str] | None = None,
    ) -> LLMResponse:
        """Generate a completion using Claude."""
        # Convert messages to Anthropic format
        anthropic_messages, system = self._convert_messages(messages)

        # Build request kwargs
        kwargs = {
            "model": self._model,
            "messages": anthropic_messages,
            "max_tokens": max_tokens,
        }

        self._apply_sampling(kwargs, temperature)

        if system:
            kwargs["system"] = system

        if stop_sequences:
            kwargs["stop_sequences"] = stop_sequences

        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        # Make API call
        response = await self._client.messages.create(**kwargs)

        # Convert response
        return self._convert_response(response)

    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Stream a completion."""
        anthropic_messages, system = self._convert_messages(messages)

        kwargs = {
            "model": self._model,
            "messages": anthropic_messages,
            "max_tokens": max_tokens,
        }

        self._apply_sampling(kwargs, temperature)

        if system:
            kwargs["system"] = system

        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text

    def _convert_messages(self, messages: list[Message]) -> tuple[list[dict], str | None]:
        """Convert messages to Anthropic format."""
        anthropic_messages = []
        system = None

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                system = msg.content
            elif msg.role == MessageRole.USER:
                anthropic_messages.append(
                    {
                        "role": "user",
                        "content": msg.content,
                    }
                )
            elif msg.role == MessageRole.ASSISTANT:
                content = []
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        content.append(
                            {
                                "type": "tool_use",
                                "id": tc.id,
                                "name": tc.name,
                                "input": tc.arguments,
                            }
                        )
                anthropic_messages.append(
                    {
                        "role": "assistant",
                        "content": content if content else msg.content,
                    }
                )
            elif msg.role == MessageRole.TOOL:
                block = {
                    "type": "tool_result",
                    "tool_use_id": msg.tool_call_id,
                    "content": msg.content,
                }
                previous = anthropic_messages[-1] if anthropic_messages else None
                if (
                    previous is not None
                    and previous["role"] == "user"
                    and isinstance(previous["content"], list)
                    and previous["content"]
                    and previous["content"][-1].get("type") == "tool_result"
                ):
                    # Results of parallel tool calls go back in one user turn.
                    previous["content"].append(block)
                else:
                    anthropic_messages.append({"role": "user", "content": [block]})

        return anthropic_messages, system

    def _convert_tools(self, tools: list[ToolDefinition]) -> list[dict]:
        """Convert tools to Anthropic format."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.parameters,
            }
            for tool in tools
        ]

    def _convert_response(self, response) -> LLMResponse:
        """Convert Anthropic response to LLMResponse."""
        text_parts = []
        tool_calls = None

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                if tool_calls is None:
                    tool_calls = []
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input,
                    )
                )

        # Concatenate all text blocks
        content = "".join(text_parts) if text_parts else None

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=response.stop_reason or "end_turn",
            usage=TokenUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            ),
            model=response.model,
            raw_response=response,
        )
