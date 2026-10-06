"""Tests for WorkflowSelectorAction's candidate list (#144).

The selector refreshes candidates from the live workflow library, falls back to the
queued ``available_workflows`` snapshot, and shows "N/A" success for unused workflows.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from zebra_agent.library import WorkflowInfo

from zebra_tasks.agent.selector import WorkflowSelectorAction


def _info(name: str, tags: list[str] | None = None, success_rate=0.0, use_count=0):
    return WorkflowInfo(
        name=name,
        description=f"{name} description",
        tags=tags or [],
        version=1,
        definition_path=Path(f"/tmp/{name}.yaml"),
        success_rate=success_rate,
        use_count=use_count,
    )


@pytest.fixture
def mock_task():
    task = MagicMock()
    task.id = "task-1"
    task.properties = {
        "goal": "Answer a question",
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


async def _select(mock_task, mock_context, workflow_name: str):
    """Run the selector with an LLM that picks *workflow_name*; return (result, prompt)."""
    response = MagicMock()
    response.content = json.dumps(
        {
            "reasoning": "fits",
            "suggested_name": None,
            "workflow_name": workflow_name,
            "create_new": False,
            "create_variant": False,
        }
    )
    response.usage = {"input_tokens": 10, "output_tokens": 5}
    provider = MagicMock()
    provider.complete = AsyncMock(return_value=response)
    with patch("zebra_tasks.agent.selector.get_provider", return_value=provider):
        result = await WorkflowSelectorAction().run(mock_task, mock_context)
    messages = (
        provider.complete.call_args.kwargs.get("messages") or (provider.complete.call_args.args[0])
    )
    prompt = "\n".join(m.content for m in messages)
    return result, prompt


class TestSelectorRefreshesFromLibrary:
    async def test_workflow_added_after_queueing_is_a_candidate(self, mock_task, mock_context):
        """A workflow missing from the queued snapshot but in the library can be used."""
        library = MagicMock()
        library.list_workflows = AsyncMock(
            return_value=[_info("Code Helper"), _info("Answer Question")]
        )
        mock_context.extras["__workflow_library__"] = library

        result, prompt = await _select(mock_task, mock_context, "Answer Question")

        assert result.next_route == "use_existing"
        assert mock_context.process.properties["workflow_name"] == "Answer Question"
        assert "Answer Question" in prompt

    async def test_system_workflows_are_not_candidates(self, mock_task, mock_context):
        library = MagicMock()
        library.list_workflows = AsyncMock(
            return_value=[_info("Code Helper"), _info("Knowledge Decay", tags=["system"])]
        )
        mock_context.extras["__workflow_library__"] = library

        result, prompt = await _select(mock_task, mock_context, "Knowledge Decay")

        assert "Knowledge Decay" not in prompt
        # Not a candidate, so the pick falls back to creating a workflow
        assert result.next_route == "create_new"

    async def test_falls_back_to_queued_list_when_listing_fails(self, mock_task, mock_context):
        library = MagicMock()
        library.list_workflows = AsyncMock(side_effect=RuntimeError("db down"))
        mock_context.extras["__workflow_library__"] = library

        result, prompt = await _select(mock_task, mock_context, "Code Helper")

        assert result.next_route == "use_existing"
        assert "Code Helper" in prompt

    async def test_uses_queued_list_without_library(self, mock_task, mock_context):
        result, prompt = await _select(mock_task, mock_context, "Code Helper")

        assert result.next_route == "use_existing"
        assert "Code Helper" in prompt


class TestSelectorSuccessRendering:
    async def test_unused_workflow_shows_na(self, mock_task, mock_context):
        library = MagicMock()
        library.list_workflows = AsyncMock(
            return_value=[
                _info("Code Helper", success_rate=0.75, use_count=4),
                _info("Answer Question"),
            ]
        )
        mock_context.extras["__workflow_library__"] = library

        _, prompt = await _select(mock_task, mock_context, "Code Helper")

        assert "success: 75%" in prompt
        assert "success: N/A" in prompt
