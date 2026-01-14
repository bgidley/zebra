"""OpenAI LLM provider."""

import os
import json
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


class OpenAIProvider(LLMProvider):
    """
    LLM provider for OpenAI models.

    Requires the 'openai' package: pip install openai
    Set OPENAI_API_KEY environment variable or pass api_key.
    """

    DEFAULT_MODEL = "gpt-4o"

    # Model context windows
    CONTEXT_WINDOWS = {
        "gpt-4o": 128000,
        "gpt-4o-mini": 128000,
        "gpt-4-turbo": 128000,
        "gpt-4": 8192,
        "gpt-3.5-turbo": 16385,
        "o1": 200000,
        "o1-mini": 128000,
    }

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        organization: str | None = None,
    ):
        try:
            import openai
        except ImportError:
            raise ImportError(
                "openai package not installed. Install with: pip install openai"
            )

        self._model = model or self.DEFAULT_MODEL
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")

        if not self._api_key:
            raise ValueError(
                "OpenAI API key required. Set OPENAI_API_KEY or pass api_key."
            )

        self._client = openai.AsyncOpenAI(
            api_key=self._api_key,
            base_url=base_url,
            organization=organization,
        )

    @property
    def name(self) -> str:
        return "openai"

    @property
    def model(self) -> str:
        return self._model

    @property
    def max_context_tokens(self) -> int:
        return self.CONTEXT_WINDOWS.get(self._model, 128000)

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stop_sequences: list[str] | None = None,
    ) -> LLMResponse:
        """Generate a completion using OpenAI."""
        # Convert messages to OpenAI format
        openai_messages = self._convert_messages(messages)

        # Build request kwargs
        kwargs = {
            "model": self._model,
            "messages": openai_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if stop_sequences:
            kwargs["stop"] = stop_sequences

        if tools:
            kwargs["tools"] = self._convert_tools(tools)
            kwargs["tool_choice"] = "auto"

        # Make API call
        response = await self._client.chat.completions.create(**kwargs)

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
        openai_messages = self._convert_messages(messages)

        kwargs = {
            "model": self._model,
            "messages": openai_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }

        if tools:
            kwargs["tools"] = self._convert_tools(tools)
            kwargs["tool_choice"] = "auto"

        stream = await self._client.chat.completions.create(**kwargs)

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def _convert_messages(self, messages: list[Message]) -> list[dict]:
        """Convert messages to OpenAI format."""
        openai_messages = []

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                openai_messages.append({
                    "role": "system",
                    "content": msg.content,
                })
            elif msg.role == MessageRole.USER:
                openai_messages.append({
                    "role": "user",
                    "content": msg.content,
                })
            elif msg.role == MessageRole.ASSISTANT:
                message = {
                    "role": "assistant",
                    "content": msg.content,
                }
                if msg.tool_calls:
                    message["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in msg.tool_calls
                    ]
                openai_messages.append(message)
            elif msg.role == MessageRole.TOOL:
                openai_messages.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id,
                    "content": msg.content,
                })

        return openai_messages

    def _convert_tools(self, tools: list[ToolDefinition]) -> list[dict]:
        """Convert tools to OpenAI format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in tools
        ]

    def _convert_response(self, response) -> LLMResponse:
        """Convert OpenAI response to LLMResponse."""
        choice = response.choices[0]
        message = choice.message

        content = message.content
        tool_calls = None

        if message.tool_calls:
            tool_calls = [
                ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments),
                )
                for tc in message.tool_calls
            ]

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            usage=TokenUsage(
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
            ),
            model=response.model,
            raw_response=response,
        )
