"""Tests for structured LLM replies: lenient parsing and one retry (#195)."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from zebra_tasks.llm.base import LLMResponse, Message, MessageRole, TokenUsage
from zebra_tasks.llm.structured import (
    RAW_KEEP_CHARS,
    LLMJSONError,
    complete_json,
    describe_failure,
    parse_llm_json,
)

GOOD = {"overall_assessment": {"health_score": 71, "key_issues": ["a"]}, "items": [1, 2]}


def _response(content: str, finish_reason: str = "end_turn") -> LLMResponse:
    return LLMResponse(
        content=content,
        tool_calls=None,
        finish_reason=finish_reason,
        usage=TokenUsage(input_tokens=10, output_tokens=20),
        model="test-model",
    )


def _provider(*responses: LLMResponse) -> MagicMock:
    provider = MagicMock()
    provider.complete = AsyncMock(side_effect=list(responses))
    return provider


MESSAGES = [Message.system("sys"), Message.user("evaluate this")]


class TestParseLlmJson:
    def test_bare_json(self):
        assert parse_llm_json(json.dumps(GOOD)) == GOOD

    def test_closed_fence(self):
        assert parse_llm_json(f"```json\n{json.dumps(GOOD)}\n```") == GOOD

    def test_fence_without_closing_fence(self):
        assert parse_llm_json(f"```json\n{json.dumps(GOOD, indent=2)}\n") == GOOD

    def test_fence_without_language(self):
        assert parse_llm_json(f"```\n{json.dumps(GOOD)}\n```") == GOOD

    def test_json_inside_prose(self):
        text = f"Here is my evaluation:\n{json.dumps(GOOD)}\nHope that helps!"
        assert parse_llm_json(text) == GOOD

    def test_list_inside_prose(self):
        assert parse_llm_json("pairs: [1, 2, 3] done") == [1, 2, 3]

    def test_truncated_reply_raises(self):
        # The prod failure: fenced JSON cut off mid-string at the token limit
        truncated = '```json\n{\n  "overall_assessment": {\n    "summary": "The system is st'
        with pytest.raises(ValueError):
            parse_llm_json(truncated)

    @pytest.mark.parametrize("content", [None, "", "not json at all"])
    def test_no_json_raises(self, content):
        with pytest.raises(ValueError):
            parse_llm_json(content)


class TestCompleteJson:
    async def test_first_reply_parses(self):
        provider = _provider(_response(json.dumps(GOOD)))

        result = await complete_json(provider, MESSAGES, temperature=0.3, max_tokens=100)

        assert result == GOOD
        assert provider.complete.await_count == 1
        assert provider.complete.await_count == 1

    async def test_truncated_then_complete_retries_with_double_tokens(self):
        provider = _provider(
            _response('```json\n{"overall_assessment": {"summ', finish_reason="max_tokens"),
            _response(json.dumps(GOOD)),
        )

        result = await complete_json(provider, MESSAGES, temperature=0.3, max_tokens=4000)

        assert result == GOOD
        assert provider.complete.await_count == 2
        first, second = provider.complete.await_args_list
        assert first.kwargs["max_tokens"] == 4000
        assert second.kwargs["max_tokens"] == 8000
        retry_user = second.kwargs["messages"][-1]
        assert retry_user.role == MessageRole.USER
        assert retry_user.content.startswith("evaluate this")
        assert "cut off at the length limit" in retry_user.content
        # System message kept; no extra turns
        assert [m.role for m in second.kwargs["messages"]] == [
            MessageRole.SYSTEM,
            MessageRole.USER,
        ]

    async def test_openai_length_finish_reason_counts_as_truncated(self):
        provider = _provider(
            _response('{"a": "b', finish_reason="length"), _response(json.dumps(GOOD))
        )

        await complete_json(provider, MESSAGES, temperature=0.3, max_tokens=500)

        assert provider.complete.await_args_list[1].kwargs["max_tokens"] == 1000

    async def test_prose_then_json_retries_with_json_only_instruction(self):
        provider = _provider(_response("I think things look fine."), _response(json.dumps(GOOD)))

        result = await complete_json(provider, MESSAGES, temperature=0.3, max_tokens=100)

        assert result == GOOD
        second = provider.complete.await_args_list[1]
        assert second.kwargs["max_tokens"] == 100
        note = second.kwargs["messages"][-1].content
        assert "only the JSON object" in note
        assert "could not be parsed as JSON (" in note

    async def test_both_fail_raises_with_failure_record(self):
        long_tail = "x" * (3 * RAW_KEEP_CHARS) + "END"
        provider = _provider(
            _response('```json\n{"a": "' + long_tail, finish_reason="max_tokens"),
            _response('```json\n{"a": "' + long_tail, finish_reason="max_tokens"),
        )

        with pytest.raises(LLMJSONError) as exc:
            await complete_json(provider, MESSAGES, temperature=0.3, max_tokens=100)

        failure = exc.value.failure
        assert failure["attempts"] == 2
        assert failure["truncated"] is True
        assert failure["finish_reason"] == "max_tokens"
        assert failure["error"]
        raw = failure["raw_response"]
        assert raw.startswith('```json\n{"a": "')
        assert raw.endswith("END")
        assert "chars omitted" in raw
        assert len(raw) < 2 * RAW_KEEP_CHARS + 100
        json.dumps(failure)  # storable as a process property
        assert provider.complete.await_count == 2
        assert "truncated at the token limit" in str(exc.value)

    async def test_provider_error_propagates(self):
        provider = MagicMock()
        provider.complete = AsyncMock(side_effect=RuntimeError("boom"))

        with pytest.raises(RuntimeError, match="boom"):
            await complete_json(provider, MESSAGES, temperature=0.3, max_tokens=100)

    async def test_note_appended_when_last_message_is_not_user(self):
        provider = _provider(_response("nope"), _response("[]"))
        messages = [Message.user("q"), Message.assistant("a")]

        await complete_json(provider, messages, temperature=0.0, max_tokens=50)

        sent = provider.complete.await_args_list[1].kwargs["messages"]
        assert len(sent) == 3
        assert sent[-1].role == MessageRole.USER


def test_describe_failure_invalid_json():
    text = describe_failure({"truncated": False, "error": "Expecting value", "attempts": 2})
    assert text == "invalid JSON: Expecting value (attempts: 2)"
