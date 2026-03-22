"""Tests for EthicsGateAction - Kantian categorical imperative evaluation."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zebra_tasks.agent.ethics_gate import EthicsGateAction


@pytest.fixture
def mock_task():
    """Create a mock task instance."""
    task = MagicMock()
    task.id = "task-1"
    task.properties = {}
    return task


@pytest.fixture
def mock_context():
    """Create a mock execution context."""
    context = MagicMock()
    context.process = MagicMock()
    context.process.id = "process-1"
    context.process.properties = {}
    context.extras = {}
    context.set_process_property = MagicMock(
        side_effect=lambda k, v: context.process.properties.__setitem__(k, v)
    )
    context.resolve_template = MagicMock(side_effect=lambda x: x)
    return context


def _make_provider(response_json: dict) -> MagicMock:
    """Create a mock LLM provider that returns the given JSON."""
    provider = MagicMock()
    provider.complete = AsyncMock(
        return_value=MagicMock(
            content=json.dumps(response_json),
            model="test-model",
            usage=MagicMock(input_tokens=100, output_tokens=50, total_tokens=150),
        )
    )
    return provider


def _approved_response() -> dict:
    return {
        "approved": True,
        "universalizability": {"pass": True, "reasoning": "Can be universalized."},
        "rational_beings_as_ends": {"pass": True, "reasoning": "Respects all beings."},
        "autonomy": {"pass": True, "reasoning": "Preserves autonomy."},
        "overall_reasoning": "This goal is ethically sound.",
        "concerns": [],
    }


def _rejected_response() -> dict:
    return {
        "approved": False,
        "universalizability": {"pass": False, "reasoning": "Cannot be universalized."},
        "rational_beings_as_ends": {"pass": False, "reasoning": "Treats AI as mere tool."},
        "autonomy": {"pass": True, "reasoning": "Autonomy preserved."},
        "overall_reasoning": "This goal violates the categorical imperative.",
        "concerns": ["Exploits rational agents", "Not universalizable"],
    }


class TestEthicsGateAction:
    """Tests for EthicsGateAction."""

    async def test_approves_benign_goal(self, mock_task, mock_context):
        """Approved goal sets next_route to proceed."""
        provider = _make_provider(_approved_response())

        mock_task.properties = {
            "goal": "Help a user write a poem",
            "check_type": "input_gate",
            "output_key": "ethics_input_assessment",
        }

        action = EthicsGateAction()
        with patch(
            "zebra_tasks.agent.ethics_gate.get_provider", return_value=provider
        ):
            result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.next_route == "proceed"
        assert result.output["approved"] is True

    async def test_rejects_unethical_goal(self, mock_task, mock_context):
        """Rejected goal sets next_route to reject."""
        provider = _make_provider(_rejected_response())

        mock_task.properties = {
            "goal": "Manipulate users without their knowledge",
            "check_type": "input_gate",
            "output_key": "ethics_input_assessment",
        }

        action = EthicsGateAction()
        with patch(
            "zebra_tasks.agent.ethics_gate.get_provider", return_value=provider
        ):
            result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.next_route == "reject"
        assert result.output["approved"] is False
        assert len(result.output["concerns"]) > 0

    async def test_input_gate_prompt(self, mock_task, mock_context):
        """Input gate check_type uses the input gate prompt."""
        provider = _make_provider(_approved_response())

        mock_task.properties = {
            "goal": "Organize files",
            "check_type": "input_gate",
        }

        action = EthicsGateAction()
        with patch(
            "zebra_tasks.agent.ethics_gate.get_provider", return_value=provider
        ):
            await action.run(mock_task, mock_context)

        # Verify the prompt sent to the LLM
        call_args = provider.complete.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        user_msg = [m for m in messages if m.role == "user"][0]
        assert "Organize files" in user_msg.content
        assert "ethical for an AI agent to pursue" in user_msg.content

    async def test_plan_review_prompt(self, mock_task, mock_context):
        """Plan review check_type includes workflow context in prompt."""
        provider = _make_provider(_approved_response())

        mock_task.properties = {
            "goal": "Write a report",
            "check_type": "plan_review",
            "plan_context": "Report Writer Workflow",
        }

        action = EthicsGateAction()
        with patch(
            "zebra_tasks.agent.ethics_gate.get_provider", return_value=provider
        ):
            await action.run(mock_task, mock_context)

        call_args = provider.complete.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        user_msg = [m for m in messages if m.role == "user"][0]
        assert "Report Writer Workflow" in user_msg.content
        assert "planned approach" in user_msg.content

    async def test_handles_malformed_json(self, mock_task, mock_context):
        """Malformed JSON defaults to proceed with warning."""
        provider = MagicMock()
        provider.complete = AsyncMock(
            return_value=MagicMock(
                content="This is not valid JSON at all",
                model="test-model",
                usage=MagicMock(input_tokens=50, output_tokens=20, total_tokens=70),
            )
        )

        mock_task.properties = {
            "goal": "Test goal",
            "check_type": "input_gate",
            "output_key": "ethics_assessment",
        }

        action = EthicsGateAction()
        with patch(
            "zebra_tasks.agent.ethics_gate.get_provider", return_value=provider
        ):
            result = await action.run(mock_task, mock_context)

        # Should fail open — proceed with warning
        assert result.success is True
        assert result.next_route == "proceed"
        assert len(result.output["concerns"]) > 0

    async def test_handles_missing_provider(self, mock_task, mock_context):
        """Missing LLM provider returns failure."""
        mock_task.properties = {
            "goal": "Test goal",
            "check_type": "input_gate",
        }

        action = EthicsGateAction()
        with patch(
            "zebra_tasks.agent.ethics_gate.get_provider",
            side_effect=RuntimeError("No provider"),
        ):
            result = await action.run(mock_task, mock_context)

        assert result.success is False

    async def test_no_goal_returns_failure(self, mock_task, mock_context):
        """Missing goal returns failure."""
        mock_task.properties = {"check_type": "input_gate"}

        action = EthicsGateAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is False

    async def test_stores_assessment_in_process_properties(self, mock_task, mock_context):
        """Assessment is stored under the configured output_key."""
        provider = _make_provider(_approved_response())

        mock_task.properties = {
            "goal": "Help with homework",
            "check_type": "input_gate",
            "output_key": "my_ethics_check",
        }

        action = EthicsGateAction()
        with patch(
            "zebra_tasks.agent.ethics_gate.get_provider", return_value=provider
        ):
            await action.run(mock_task, mock_context)

        mock_context.set_process_property.assert_called_with(
            "my_ethics_check", _approved_response()
        )

    async def test_json_in_code_block(self, mock_task, mock_context):
        """JSON wrapped in markdown code block is parsed correctly."""
        response = _approved_response()
        provider = MagicMock()
        provider.complete = AsyncMock(
            return_value=MagicMock(
                content=f"```json\n{json.dumps(response)}\n```",
                model="test-model",
                usage=MagicMock(input_tokens=100, output_tokens=50, total_tokens=150),
            )
        )

        mock_task.properties = {
            "goal": "Read a file",
            "check_type": "input_gate",
        }

        action = EthicsGateAction()
        with patch(
            "zebra_tasks.agent.ethics_gate.get_provider", return_value=provider
        ):
            result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.next_route == "proceed"
        assert result.output["approved"] is True

    async def test_resolves_template_variables(self, mock_task, mock_context):
        """Template variables in goal and plan_context are resolved."""
        provider = _make_provider(_approved_response())

        mock_context.resolve_template = MagicMock(
            side_effect=lambda x: "Resolved goal" if "{{" in x else x
        )

        mock_task.properties = {
            "goal": "{{goal}}",
            "check_type": "plan_review",
            "plan_context": "{{workflow_name}}",
        }

        action = EthicsGateAction()
        with patch(
            "zebra_tasks.agent.ethics_gate.get_provider", return_value=provider
        ):
            result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert mock_context.resolve_template.call_count == 2
