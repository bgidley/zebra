"""Testing utilities for LLM providers."""

import hashlib
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from zebra_tasks.llm.base import (
    LLMProvider,
    LLMResponse,
    Message,
    TokenUsage,
    ToolCall,
    ToolDefinition,
)


def _hash_request(
    messages: list[Message],
    tools: list[ToolDefinition] | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    stop_sequences: list[str] | None = None,
) -> str:
    """Create a deterministic hash for a given request."""
    # We only care about the semantic content, not exact object references
    msg_repr = [{"role": m.role.value, "content": m.content, "name": m.name} for m in messages]
    tools_repr = [{"name": t.name} for t in (tools or [])]

    payload = json.dumps(
        {
            "messages": msg_repr,
            "tools": tools_repr,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stop_sequences": stop_sequences,
        },
        sort_keys=True,
    )

    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class CassetteProvider(LLMProvider):
    """
    LLM provider that records and replays interactions to a JSON tape.
    """

    def __init__(self, wrapped: LLMProvider, cassette_path: str | Path, record_mode: str = "once"):
        """
        Args:
            wrapped: The actual provider to wrap (e.g., AnthropicProvider).
            cassette_path: Path to the JSON cassette file.
            record_mode: 'once' (record if missing), 'rewrite' (always record),
                'none' (never record, fail if missing).
        """
        self.wrapped = wrapped
        self.cassette_path = Path(cassette_path)
        self.record_mode = record_mode
        self._cassette: dict[str, dict[str, Any]] = self._load_cassette()

    def _load_cassette(self) -> dict[str, dict[str, Any]]:
        if self.cassette_path.exists():
            with open(self.cassette_path, encoding="utf-8") as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return {}
        return {}

    def _save_cassette(self, key: str, data: dict[str, Any]) -> None:
        self.cassette_path.parent.mkdir(parents=True, exist_ok=True)
        # Read current state first to avoid overwriting
        current = self._load_cassette()
        current[key] = data
        self._cassette = current  # update local cache
        with open(self.cassette_path, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2, sort_keys=True)

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stop_sequences: list[str] | None = None,
    ) -> LLMResponse:
        req_hash = _hash_request(messages, tools, temperature, max_tokens, stop_sequences)
        key = f"complete_{req_hash}"

        self._cassette = self._load_cassette()

        if self.record_mode == "rewrite" or (
            self.record_mode == "once" and key not in self._cassette
        ):
            # Record
            response = await self.wrapped.complete(
                messages, tools, temperature, max_tokens, stop_sequences
            )
            data = {
                "content": response.content,
                "finish_reason": response.finish_reason,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
                "model": response.model,
                "tool_calls": [
                    {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                    for tc in (response.tool_calls or [])
                ],
            }
            self._save_cassette(key, data)
            return response

        if key not in self._cassette:
            raise ValueError(
                f"Interaction not found in cassette {self.cassette_path} and record_mode is 'none'."
            )

        # Replay
        data = self._cassette[key]
        tool_calls = [
            ToolCall(id=tc["id"], name=tc["name"], arguments=tc["arguments"])
            for tc in data.get("tool_calls", [])
        ]

        return LLMResponse(
            content=data["content"],
            tool_calls=tool_calls if tool_calls else None,
            finish_reason=data["finish_reason"],
            usage=TokenUsage(**data["usage"]),
            model=data["model"],
            raw_response=None,
        )

    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        req_hash = _hash_request(messages, tools, temperature, max_tokens)
        key = f"stream_{req_hash}"

        self._cassette = self._load_cassette()

        if self.record_mode == "rewrite" or (
            self.record_mode == "once" and key not in self._cassette
        ):
            chunks = []
            async for chunk in self.wrapped.stream(messages, tools, temperature, max_tokens):
                chunks.append(chunk)
                yield chunk

            self._save_cassette(key, {"chunks": chunks})
            return

        if key not in self._cassette:
            raise ValueError(
                f"Stream interaction not found in cassette {self.cassette_path} "
                "and record_mode is 'none'."
            )

        for chunk in self._cassette[key]["chunks"]:
            yield chunk

    @property
    def name(self) -> str:
        return self.wrapped.name

    @property
    def model(self) -> str:
        return self.wrapped.model

    @property
    def max_context_tokens(self) -> int:
        return self.wrapped.max_context_tokens
