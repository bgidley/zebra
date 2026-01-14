"""Anthropic Claude LLM provider."""

import os
from typing import AsyncIterator

from zebra_tasks.llm.base import (
    LLMProvider,
    LLMResponse,
    Message,
    MessageRole,
    TokenUsage,
    ToolCall,
    ToolDefinition,
)


class AnthropicProvider(LLMProvider):
    """
    LLM provider for Anthropic Claude models.

    Requires the 'anthropic' package: pip install anthropic
    Set ANTHROPIC_API_KEY environment variable or pass api_key.
    """

    DEFAULT_MODEL = "claude-sonnet-4-20250514"

    # Model context windows
    CONTEXT_WINDOWS = {
        "claude-opus-4-20250514": 200000,
        "claude-sonnet-4-20250514": 200000,
        "claude-3-5-sonnet-20241022": 200000,
        "claude-3-5-haiku-20241022": 200000,
        "claude-3-opus-20240229": 200000,
        "claude-3-sonnet-20240229": 200000,
        "claude-3-haiku-20240307": 200000,
    }

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

        self._model = model or self.DEFAULT_MODEL
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")

        if not self._api_key:
            raise ValueError(
                "Anthropic API key required. Set ANTHROPIC_API_KEY or pass api_key."
            )

        self._client = anthropic.AsyncAnthropic(
            api_key=self._api_key,
            base_url=base_url,
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
            "temperature": temperature,
        }

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
            "temperature": temperature,
        }

        if system:
            kwargs["system"] = system

        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text

    def _convert_messages(
        self, messages: list[Message]
    ) -> tuple[list[dict], str | None]:
        """Convert messages to Anthropic format."""
        anthropic_messages = []
        system = None

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                system = msg.content
            elif msg.role == MessageRole.USER:
                anthropic_messages.append({
                    "role": "user",
                    "content": msg.content,
                })
            elif msg.role == MessageRole.ASSISTANT:
                content = []
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        content.append({
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.arguments,
                        })
                anthropic_messages.append({
                    "role": "assistant",
                    "content": content if content else msg.content,
                })
            elif msg.role == MessageRole.TOOL:
                anthropic_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,
                        "content": msg.content,
                    }],
                })

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
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input,
                ))

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
