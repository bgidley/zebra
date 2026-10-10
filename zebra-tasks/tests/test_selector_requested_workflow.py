"""Tests for WorkflowSelectorAction honouring ``requested_workflow`` (F155)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zebra_tasks.agent.selector import WorkflowSelectorAction

WORKFLOWS = [
    {"name": "Web Research", "description": "Search the web", "tags": ["web"]},
    {"name": "Daily News Reading", "description": "Read the news", "tags": ["news"]},
]


@pytest.fixture
def mock_task():
    task = MagicMock()
    task.id = "task-1"
    task.properties = {
        "goal": "Read today's news from news.kagi.com",
        "available_workflows": json.dumps(WORKFLOWS),
        "output_key": "selection",
    }
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


def _provider(workflow_name: str) -> MagicMock:
    response = MagicMock()
    response.content = json.dumps(
        {
            "workflow_name": workflow_name,
            "create_new": False,
            "create_variant": False,
            "reasoning": "llm pick",
        }
    )
    provider = MagicMock()
    provider.complete = AsyncMock(return_value=response)
    return provider


async def test_requested_workflow_is_used_without_llm(mock_task, mock_context):
    mock_context.process.properties["requested_workflow"] = "Daily News Reading"
    provider = _provider("Web Research")

    with patch("zebra_tasks.agent.selector.get_provider", return_value=provider):
        result = await WorkflowSelectorAction().run(mock_task, mock_context)

    provider.complete.assert_not_awaited()
    assert result.success
    assert result.next_route == "use_existing"
    assert result.output["workflow_name"] == "Daily News Reading"
    assert mock_context.process.properties["workflow_name"] == "Daily News Reading"
    assert mock_context.process.properties["selection"]["create_new"] is False


async def test_missing_requested_workflow_falls_back_to_llm(mock_task, mock_context):
    mock_context.process.properties["requested_workflow"] = "Retired Workflow"
    provider = _provider("Web Research")

    with patch("zebra_tasks.agent.selector.get_provider", return_value=provider):
        result = await WorkflowSelectorAction().run(mock_task, mock_context)

    provider.complete.assert_awaited_once()
    assert result.output["workflow_name"] == "Web Research"
    assert result.next_route == "use_existing"


async def test_no_requested_workflow_uses_llm(mock_task, mock_context):
    provider = _provider("Daily News Reading")

    with patch("zebra_tasks.agent.selector.get_provider", return_value=provider):
        result = await WorkflowSelectorAction().run(mock_task, mock_context)

    provider.complete.assert_awaited_once()
    assert result.output["reasoning"] == "llm pick"
