"""Tests for WorkflowSelectorAction knowledge_context integration."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_task():
    task = MagicMock()
    task.id = "task-1"
    task.properties = {
        "goal": "Write a Python script",
        "available_workflows": json.dumps(
            [
                {
                    "name": "Code Helper",
                    "description": "Helps write code",
                    "tags": ["code"],
                    "success_rate": 0.9,
                    "use_count": 5,
                    "use_when": "User wants to write code",
                }
            ]
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


@pytest.fixture
def mock_llm_response():
    response = MagicMock()
    response.content = json.dumps(
        {
            "workflow_name": "Code Helper",
            "create_new": False,
            "create_variant": False,
            "reasoning": "Good fit",
            "suggested_name": None,
        }
    )
    response.usage = {"input_tokens": 100, "output_tokens": 50}
    return response


class TestWorkflowSelectorKnowledge:
    async def test_knowledge_context_included_in_prompt(
        self, mock_task, mock_context, mock_llm_response
    ):
        """When knowledge_context is provided, it appears in the LLM user message."""
        from zebra_tasks.agent.selector import WorkflowSelectorAction

        mock_task.properties["knowledge_context"] = "[preferences] language: Python"

        captured_messages = []

        async def mock_complete(messages, **kwargs):
            captured_messages.extend(messages)
            return mock_llm_response

        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(side_effect=mock_complete)

        with patch("zebra_tasks.agent.selector.get_provider", return_value=mock_provider):
            action = WorkflowSelectorAction()
            result = await action.run(mock_task, mock_context)

        assert result.success
        user_content = next((m.content for m in captured_messages if m.role == "user"), "")
        assert "## Personal Knowledge" in user_content
        assert "[preferences] language: Python" in user_content

    async def test_no_knowledge_context_omitted_from_prompt(
        self, mock_task, mock_context, mock_llm_response
    ):
        """When knowledge_context is empty, no Personal Knowledge section is added."""
        from zebra_tasks.agent.selector import WorkflowSelectorAction

        mock_task.properties["knowledge_context"] = ""

        captured_messages = []

        async def mock_complete(messages, **kwargs):
            captured_messages.extend(messages)
            return mock_llm_response

        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(side_effect=mock_complete)

        with patch("zebra_tasks.agent.selector.get_provider", return_value=mock_provider):
            action = WorkflowSelectorAction()
            result = await action.run(mock_task, mock_context)

        assert result.success
        user_content = next((m.content for m in captured_messages if m.role == "user"), "")
        assert "## Personal Knowledge" not in user_content

    async def test_missing_knowledge_context_property_omitted(
        self, mock_task, mock_context, mock_llm_response
    ):
        """When knowledge_context is not in properties, no Personal Knowledge section is added."""
        from zebra_tasks.agent.selector import WorkflowSelectorAction

        # Don't set knowledge_context at all
        mock_task.properties.pop("knowledge_context", None)

        captured_messages = []

        async def mock_complete(messages, **kwargs):
            captured_messages.extend(messages)
            return mock_llm_response

        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(side_effect=mock_complete)

        with patch("zebra_tasks.agent.selector.get_provider", return_value=mock_provider):
            action = WorkflowSelectorAction()
            result = await action.run(mock_task, mock_context)

        assert result.success
        user_content = next((m.content for m in captured_messages if m.role == "user"), "")
        assert "## Personal Knowledge" not in user_content
