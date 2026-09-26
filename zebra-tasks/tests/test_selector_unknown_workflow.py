"""Tests for WorkflowSelectorAction falling back when the LLM picks a missing workflow."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zebra_tasks.agent.selector import WorkflowSelectorAction


@pytest.fixture
def mock_task():
    task = MagicMock()
    task.id = "task-1"
    task.properties = {
        "goal": "Count from 1 to 100",
        "available_workflows": json.dumps(
            [{"name": "Code Helper", "description": "Helps write code", "tags": ["code"]}]
        ),
    }
    return task


@pytest.fixture
def mock_context():
    context = MagicMock()
    context.process = MagicMock()
    context.process.id = "process-1"
    context.process.properties = {}
    context.extras = {}
    context.get_process_property = MagicMock(
        side_effect=lambda k, d=None: context.process.properties.get(k, d)
    )
    context.set_process_property = MagicMock(
        side_effect=lambda k, v: context.process.properties.__setitem__(k, v)
    )
    context.resolve_template = MagicMock(side_effect=lambda x: x)
    return context


async def _select(mock_task, mock_context, llm_choice: dict):
    response = MagicMock()
    response.content = json.dumps(
        {"reasoning": "memory says so", "suggested_name": None, **llm_choice}
    )
    response.usage = {"input_tokens": 10, "output_tokens": 5}
    provider = MagicMock()
    provider.complete = AsyncMock(return_value=response)
    with patch("zebra_tasks.agent.selector.get_provider", return_value=provider):
        return await WorkflowSelectorAction().run(mock_task, mock_context)


class TestSelectorUnknownWorkflow:
    async def test_missing_workflow_falls_back_to_create_new(self, mock_task, mock_context):
        """A use_existing pick that isn't in the library routes to create_new."""
        result = await _select(
            mock_task,
            mock_context,
            {"workflow_name": "Basic Hello", "create_new": False, "create_variant": False},
        )

        assert result.success
        assert result.next_route == "create_new"
        assert result.output["workflow_name"] is None
        assert result.output["suggested_name"] == "Basic Hello"
        assert "workflow_name" not in mock_context.process.properties

    async def test_missing_variant_source_falls_back_to_create_new(self, mock_task, mock_context):
        """A create_variant whose source workflow is missing routes to create_new."""
        result = await _select(
            mock_task,
            mock_context,
            {"workflow_name": "Gone Workflow", "create_new": False, "create_variant": True},
        )

        assert result.next_route == "create_new"
        assert result.output["create_variant"] is False

    async def test_existing_workflow_is_used(self, mock_task, mock_context):
        """A pick that exists in the library is executed as before."""
        result = await _select(
            mock_task,
            mock_context,
            {"workflow_name": "Code Helper", "create_new": False, "create_variant": False},
        )

        assert result.next_route == "use_existing"
        assert mock_context.process.properties["workflow_name"] == "Code Helper"
