"""Tests for contextual reversibility assessment (F14 / REQ-TRUST-002)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zebra_tasks.agent.reversibility import (
    ReversibilityAssessment,
    assess_reversibility,
)


@pytest.fixture
def mock_context():
    context = MagicMock()
    context.process = MagicMock()
    context.process.properties = {}
    context.extras = {}
    return context


def _make_provider(content: str) -> MagicMock:
    provider = MagicMock()
    provider.complete = AsyncMock(
        return_value=MagicMock(content=content, model="test-model", usage=MagicMock())
    )
    return provider


def _verdict(reversible: bool, **extra) -> str:
    payload = {
        "reversible": reversible,
        "reasoning": "because",
        "confidence": 0.9,
        "chain_notes": "none",
    }
    payload.update(extra)
    return json.dumps(payload)


class TestHintShortCircuit:
    async def test_always_reversible_skips_llm(self, mock_context):
        with patch("zebra_tasks.agent.reversibility.get_provider") as get_provider:
            assessment = await assess_reversibility(
                "file_read", "always_reversible", {"path": "/x"}, "read a file", mock_context
            )

        get_provider.assert_not_called()
        assert assessment.reversible is True
        assert assessment.source == "hint"
        assert assessment.confidence == 1.0

    async def test_always_irreversible_skips_llm(self, mock_context):
        with patch("zebra_tasks.agent.reversibility.get_provider") as get_provider:
            assessment = await assess_reversibility(
                "send_email", "always_irreversible", {}, "send", mock_context
            )

        get_provider.assert_not_called()
        assert assessment.reversible is False
        assert assessment.source == "hint"


class TestLLMPath:
    async def test_reversible_verdict(self, mock_context):
        provider = _make_provider(_verdict(True))
        with patch("zebra_tasks.agent.reversibility.get_provider", return_value=provider):
            assessment = await assess_reversibility(
                "file_delete",
                "context_dependent",
                {"path": "/tmp/scratch"},
                "delete temp files",
                mock_context,
            )

        assert assessment.reversible is True
        assert assessment.source == "llm"
        assert assessment.reasoning == "because"
        assert assessment.confidence == 0.9

    async def test_irreversible_verdict(self, mock_context):
        provider = _make_provider(_verdict(False, chain_notes="config loss is permanent"))
        with patch("zebra_tasks.agent.reversibility.get_provider", return_value=provider):
            assessment = await assess_reversibility(
                "file_delete",
                "context_dependent",
                {"path": "/etc/zebra/prod.conf"},
                "delete config",
                mock_context,
            )

        assert assessment.reversible is False
        assert assessment.chain_notes == "config loss is permanent"

    async def test_code_fenced_json_parsed(self, mock_context):
        provider = _make_provider(f"```json\n{_verdict(True)}\n```")
        with patch("zebra_tasks.agent.reversibility.get_provider", return_value=provider):
            assessment = await assess_reversibility("x", "context_dependent", {}, "", mock_context)

        assert assessment.reversible is True
        assert assessment.source == "llm"

    async def test_prompt_contains_parameters_and_declaration(self, mock_context):
        provider = _make_provider(_verdict(True))
        with patch("zebra_tasks.agent.reversibility.get_provider", return_value=provider):
            await assess_reversibility(
                "file_delete",
                "context_dependent",
                {"path": "/etc/zebra/prod.conf", "recursive": True},
                "delete config",
                mock_context,
                declared="reversible",
            )

        messages = provider.complete.call_args.kwargs["messages"]
        user_prompt = messages[1].content
        assert "/etc/zebra/prod.conf" in user_prompt
        assert "recursive" in user_prompt
        assert "reversible" in user_prompt  # the untrusted declaration
        assert "file_delete" in user_prompt

    async def test_default_model_is_haiku(self, mock_context):
        provider = _make_provider(_verdict(True))
        with patch(
            "zebra_tasks.agent.reversibility.get_provider", return_value=provider
        ) as get_provider:
            await assess_reversibility("x", "context_dependent", {}, "", mock_context)

        get_provider.assert_called_once_with("anthropic", "haiku")

    async def test_model_override(self, mock_context):
        provider = _make_provider(_verdict(True))
        with patch(
            "zebra_tasks.agent.reversibility.get_provider", return_value=provider
        ) as get_provider:
            await assess_reversibility(
                "x", "context_dependent", {}, "", mock_context, model="sonnet"
            )

        get_provider.assert_called_once_with("anthropic", "sonnet")


class TestFailClosed:
    async def test_unparseable_response_fails_closed(self, mock_context):
        provider = _make_provider("I think it is probably fine to proceed.")
        with patch("zebra_tasks.agent.reversibility.get_provider", return_value=provider):
            assessment = await assess_reversibility("x", "context_dependent", {}, "", mock_context)

        assert assessment.reversible is False
        assert assessment.source == "fail_closed"

    async def test_provider_error_fails_closed(self, mock_context):
        provider = MagicMock()
        provider.complete = AsyncMock(side_effect=RuntimeError("api down"))
        with patch("zebra_tasks.agent.reversibility.get_provider", return_value=provider):
            assessment = await assess_reversibility("x", "context_dependent", {}, "", mock_context)

        assert assessment.reversible is False
        assert assessment.source == "fail_closed"

    async def test_provider_lookup_error_fails_closed(self, mock_context):
        with patch(
            "zebra_tasks.agent.reversibility.get_provider", side_effect=ValueError("no key")
        ):
            assessment = await assess_reversibility("x", "context_dependent", {}, "", mock_context)

        assert assessment.reversible is False
        assert assessment.source == "fail_closed"

    async def test_missing_verdict_field_fails_closed(self, mock_context):
        provider = _make_provider(json.dumps({"reasoning": "no verdict"}))
        with patch("zebra_tasks.agent.reversibility.get_provider", return_value=provider):
            assessment = await assess_reversibility("x", "context_dependent", {}, "", mock_context)

        assert assessment.reversible is False
        assert assessment.source == "fail_closed"


class TestSerialisation:
    def test_to_dict_is_json_serialisable(self):
        assessment = ReversibilityAssessment(
            reversible=True, reasoning="r", confidence=0.5, chain_notes="c", source="llm"
        )
        assert json.loads(json.dumps(assessment.to_dict())) == {
            "reversible": True,
            "reasoning": "r",
            "confidence": 0.5,
            "chain_notes": "c",
            "source": "llm",
        }
