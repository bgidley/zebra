"""Structured (JSON) replies from an LLM: lenient parsing and one retry (#195).

LLM replies that should be JSON arrive wrapped in code fences, surrounded by
prose, or cut off at the token limit. ``parse_llm_json`` extracts what it can;
``complete_json`` retries an unusable reply once and, if that also fails,
raises ``LLMJSONError`` carrying why, so the caller can record the cause
instead of a bare "parsing failed".
"""

import json
import logging
import re
from typing import Any

from zebra_tasks.llm.base import LLMProvider, Message, MessageRole

logger = logging.getLogger(__name__)

# finish_reason values meaning the reply hit max_tokens (OpenAI-compatible: OpenRouter)
TRUNCATED_FINISH_REASONS = frozenset({"max_tokens", "length"})
# Characters kept from each end of an unusable reply
RAW_KEEP_CHARS = 2000

_OPENING_FENCE_RE = re.compile(r"```[A-Za-z0-9_-]*[ \t]*\n?")

TRUNCATED_RETRY_NOTE = (
    "Your previous reply was cut off at the length limit before the JSON was complete. "
    "Reply again with only the JSON object, and keep every string brief."
)
INVALID_RETRY_NOTE = (
    "Your previous reply could not be parsed as JSON ({error}). "
    "Reply again with only the JSON object: no prose and no code fences."
)


class LLMJSONError(ValueError):
    """No usable JSON in the LLM's replies.

    Attributes:
        failure: JSON-serialisable record of the last attempt: ``error``,
            ``finish_reason``, ``truncated``, ``attempts`` and ``raw_response``
            (start and end of the reply, capped).
    """

    def __init__(self, failure: dict[str, Any]):
        self.failure = failure
        super().__init__(describe_failure(failure))


def describe_failure(failure: dict[str, Any]) -> str:
    """One-line cause of a failed structured reply, for key issues and error lists."""
    if failure.get("truncated"):
        cause = "reply truncated at the token limit"
    else:
        cause = f"invalid JSON: {failure.get('error')}"
    return f"{cause} (attempts: {failure.get('attempts')})"


def parse_llm_json(content: str | None) -> Any:
    """Parse a JSON value from an LLM reply.

    Accepts a bare JSON value, one inside a code fence (closing fence optional,
    so a truncated reply is still tried), or one surrounded by prose.

    Raises:
        ValueError: No JSON value could be parsed; the message is the JSON error.
    """
    text = (content or "").strip()
    fence = _OPENING_FENCE_RE.search(text)
    if fence:
        end = text.find("```", fence.end())
        text = text[fence.end() : end if end != -1 else None].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        first_error = e
    span = _outer_span(text)
    if span is not None:
        try:
            return json.loads(span)
        except json.JSONDecodeError:
            pass
    raise ValueError(str(first_error)) from first_error


def _outer_span(text: str) -> str | None:
    """The text from the first ``{``/``[`` to the last matching closer, if any."""
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        return None
    start = min(starts)
    end = text.rfind("}" if text[start] == "{" else "]")
    return text[start : end + 1] if end > start else None


async def complete_json(
    provider: LLMProvider,
    messages: list[Message],
    *,
    temperature: float,
    max_tokens: int,
) -> Any:
    """Ask for a JSON reply, retrying once if it cannot be parsed.

    A truncated reply is retried with twice ``max_tokens`` and a request to be
    brief; any other unparseable reply with a JSON-only instruction. The note is
    appended to the last user message so message ordering stays valid for every
    provider.

    Args:
        provider: LLM provider to call.
        messages: Conversation, normally system + user.
        temperature: Sampling temperature.
        max_tokens: Token budget for the first attempt.

    Returns:
        The parsed JSON value.

    Raises:
        LLMJSONError: Neither reply could be parsed.
        Exception: Provider errors propagate unchanged.
    """
    attempt_messages = messages
    attempt_tokens = max_tokens
    for attempt in (1, 2):
        response = await provider.complete(
            messages=attempt_messages, temperature=temperature, max_tokens=attempt_tokens
        )
        try:
            return parse_llm_json(response.content)
        except ValueError as e:
            truncated = response.finish_reason in TRUNCATED_FINISH_REASONS
            failure = {
                "error": str(e),
                "finish_reason": response.finish_reason,
                "truncated": truncated,
                "attempts": attempt,
                "raw_response": _clip(response.content or ""),
            }
            logger.warning(
                "Unusable JSON reply (attempt %d, finish_reason=%s): %s",
                attempt,
                response.finish_reason,
                e,
            )
        if truncated:
            note, attempt_tokens = TRUNCATED_RETRY_NOTE, max_tokens * 2
        else:
            note = INVALID_RETRY_NOTE.format(error=failure["error"])
        attempt_messages = _with_note(messages, note)
    raise LLMJSONError(failure)


def _with_note(messages: list[Message], note: str) -> list[Message]:
    """Copy of *messages* with *note* appended to the last user message."""
    if messages and messages[-1].role == MessageRole.USER:
        return [*messages[:-1], Message.user(f"{messages[-1].content}\n\n{note}")]
    return [*messages, Message.user(note)]


def _clip(text: str) -> str:
    """Keep the start and end of a long reply; the end shows where it stopped."""
    if len(text) <= 2 * RAW_KEEP_CHARS:
        return text
    omitted = len(text) - 2 * RAW_KEEP_CHARS
    return f"{text[:RAW_KEEP_CHARS]}\n… [{omitted} chars omitted] …\n{text[-RAW_KEEP_CHARS:]}"
