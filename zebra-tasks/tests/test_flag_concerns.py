"""Tests for FlagConcernsAction - proactive, advisory concern flagging (F21)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zebra_tasks.agent.flag_concerns import FlagConcernsAction


@pytest.fixture
def mock_task():
    task = MagicMock()
    task.id = "task-1"
    task.properties = {}
    return task


@pytest.fixture
def mock_context():
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


def _make_provider(content: str) -> MagicMock:
    provider = MagicMock()
    provider.complete = AsyncMock(
        return_value=MagicMock(
            content=content,
            model="test-model",
            usage=MagicMock(input_tokens=100, output_tokens=50, total_tokens=150),
        )
    )
    return provider


class TestFlagConcernsAction:
    async def test_flags_concerns_and_never_blocks(self, mock_task, mock_context):
        """Concerns are stored on the process; the action never sets a reject route."""
        response = {
            "concerns": [
                {
                    "description": "Deletes user files irreversibly",
                    "severity": "high",
                    "step": "cleanup",
                }
            ],
            "summary": "One high-severity concern flagged.",
        }
        provider = _make_provider(json.dumps(response))
        mock_task.properties = {
            "goal": "Clean up my downloads folder",
            "plan_context": "File Operations",
            "output_key": "planning_concerns",
        }

        action = FlagConcernsAction()
        with patch("zebra_tasks.agent.flag_concerns.get_provider", return_value=provider):
            result = await action.run(mock_task, mock_context)

        assert result.success is True
        # Advisory: no routing verdict at all
        assert result.next_route is None
        assert result.output["concerns"][0]["severity"] == "high"
        stored = mock_context.process.properties["planning_concerns"]
        assert stored["concerns"][0]["description"] == "Deletes user files irreversibly"

    async def test_routine_plan_returns_empty(self, mock_task, mock_context):
        """A low-risk plan yields an empty concerns list (no invented concerns)."""
        provider = _make_provider(json.dumps({"concerns": [], "summary": "Routine, low risk."}))
        mock_task.properties = {"goal": "Summarise this article", "plan_context": "Summarize Text"}

        action = FlagConcernsAction()
        with patch("zebra_tasks.agent.flag_concerns.get_provider", return_value=provider):
            result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.output["concerns"] == []

    async def test_uses_haiku_by_default(self, mock_task, mock_context):
        """The advisory scan defaults to the cheap haiku model."""
        provider = _make_provider(json.dumps({"concerns": [], "summary": "ok"}))
        mock_task.properties = {"goal": "Do a thing"}

        action = FlagConcernsAction()
        with patch(
            "zebra_tasks.agent.flag_concerns.get_provider", return_value=provider
        ) as get_provider:
            await action.run(mock_task, mock_context)

        # get_provider(provider_name, model) — second positional arg is the model
        assert get_provider.call_args.args[1] == "haiku"

    async def test_unparseable_response_degrades_gracefully(self, mock_task, mock_context):
        """A non-JSON response yields empty concerns and still succeeds."""
        provider = _make_provider("not json at all")
        mock_task.properties = {"goal": "Do a thing", "plan_context": "Some Workflow"}

        action = FlagConcernsAction()
        with patch("zebra_tasks.agent.flag_concerns.get_provider", return_value=provider):
            result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.output["concerns"] == []
        assert "planning_concerns" in mock_context.process.properties

    async def test_provider_error_degrades_gracefully(self, mock_task, mock_context):
        """If the provider cannot be constructed, the action still succeeds advisorily."""
        mock_task.properties = {"goal": "Do a thing"}

        action = FlagConcernsAction()
        with patch(
            "zebra_tasks.agent.flag_concerns.get_provider", side_effect=RuntimeError("no key")
        ):
            result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.output["concerns"] == []

    async def test_missing_goal_returns_empty(self, mock_task, mock_context):
        """No goal means nothing to review — empty concerns, no LLM call."""
        mock_task.properties = {}

        action = FlagConcernsAction()
        with patch("zebra_tasks.agent.flag_concerns.get_provider") as get_provider:
            result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.output["concerns"] == []
        get_provider.assert_not_called()
