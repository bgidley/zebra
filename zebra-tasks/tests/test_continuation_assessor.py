"""Tests for ContinuationAssessorAction (F135)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zebra_tasks.agent.continuation_assessor import ContinuationAssessorAction

PREVIOUS = {
    "run_id": "run-1",
    "goal": "Research bikes",
    "workflow_name": "Brainstorm Ideas",
    "success": False,
    "output": "Partial list",
    "task_progress": [
        {"task_name": "Gather", "state": "complete"},
        {"task_name": "Rank", "state": "failed"},
    ],
}


class _Library:
    def __init__(self, names):
        self.names = set(names)

    def get_workflow(self, name):
        if name not in self.names:
            raise ValueError(name)
        return MagicMock()


@pytest.fixture
def task():
    t = MagicMock()
    t.id = "task-1"
    t.properties = {"goal": "Finish the ranking", "output_key": "continuation_assessment"}
    return t


def _context(properties, library=None):
    context = MagicMock()
    context.process = MagicMock()
    context.process.properties = properties
    context.extras = {"__workflow_library__": library} if library is not None else {}
    context.set_process_property = MagicMock(
        side_effect=lambda k, v: context.process.properties.__setitem__(k, v)
    )
    context.resolve_template = MagicMock(side_effect=lambda x: x)
    return context


def _provider(content=None, error=None):
    provider = MagicMock()
    if error:
        provider.complete = AsyncMock(side_effect=error)
    else:
        response = MagicMock()
        response.content = content
        provider.complete = AsyncMock(return_value=response)
    return provider


async def _run(task, context, provider):
    with patch(
        "zebra_tasks.agent.continuation_assessor.get_provider", return_value=provider
    ) as get_provider:
        result = await ContinuationAssessorAction().run(task, context)
    return result, get_provider


def _continuation_props(**extra):
    return {"previous_run_context": dict(PREVIOUS), **extra}


async def test_non_continuation_passes_through_without_llm(task):
    context = _context({"goal": "Fresh goal"})
    result, get_provider = await _run(task, context, _provider("{}"))

    assert result.success
    assert result.next_route == "not_continuation"
    get_provider.assert_not_called()
    context.set_process_property.assert_not_called()


async def test_same_workflow_sets_workflow_and_selection(task):
    content = json.dumps({"decision": "same_workflow", "rationale": "Retry the ranking"})
    props = _continuation_props(continuation_comment="Ranking step crashed")
    context = _context(props, _Library(["Brainstorm Ideas"]))
    provider = _provider(content)

    result, _ = await _run(task, context, provider)

    assert result.next_route == "same_workflow"
    assert props["continuation_decision"] == "same_workflow"
    assert props["continuation_rationale"] == "Retry the ranking"
    assert props["workflow_name"] == "Brainstorm Ideas"
    assert props["selection"]["workflow_name"] == "Brainstorm Ideas"
    assert props["selection"]["reasoning"] == "Retry the ranking"
    assert result.output["workflow_name"] == "Brainstorm Ideas"

    # The LLM saw the comment, the previous workflow and the task progress
    prompt = provider.complete.call_args.kwargs["messages"][1].content
    assert "Ranking step crashed" in prompt
    assert "Brainstorm Ideas" in prompt
    assert "- Rank: failed" in prompt


async def test_existing_workflow_routes_to_selector(task):
    content = "```json\n" + json.dumps({"decision": "existing_workflow", "rationale": "x"}) + "```"
    props = _continuation_props()
    context = _context(props, _Library(["Brainstorm Ideas"]))

    result, _ = await _run(task, context, _provider(content))

    assert result.next_route == "existing_workflow"
    assert props["continuation_decision"] == "existing_workflow"
    assert "selection" not in props
    assert "workflow_name" not in props


async def test_new_workflow_sets_create_new_selection(task):
    content = json.dumps(
        {"decision": "new_workflow", "rationale": "Nothing fits", "suggested_name": "Bike Ranker"}
    )
    props = _continuation_props()
    context = _context(props, _Library(["Brainstorm Ideas"]))

    result, _ = await _run(task, context, _provider(content))

    assert result.next_route == "new_workflow"
    assert props["selection"]["create_new"] is True
    assert props["selection"]["suggested_name"] == "Bike Ranker"
    assert "workflow_name" not in props


async def test_same_workflow_missing_from_library_falls_back(task):
    content = json.dumps({"decision": "same_workflow", "rationale": "Again"})
    props = _continuation_props()
    context = _context(props, _Library([]))

    result, _ = await _run(task, context, _provider(content))

    assert result.next_route == "existing_workflow"
    assert props["continuation_decision"] == "existing_workflow"
    assert "no longer available" in props["continuation_rationale"]
    assert "workflow_name" not in props


async def test_same_workflow_checks_available_workflows_without_library(task):
    task.properties["available_workflows"] = [{"name": "Brainstorm Ideas"}]
    content = json.dumps({"decision": "same_workflow", "rationale": "Again"})
    props = _continuation_props()

    result, _ = await _run(task, _context(props), _provider(content))

    assert result.next_route == "same_workflow"


@pytest.mark.parametrize(
    "provider",
    [
        _provider(error=RuntimeError("API down")),
        _provider("not json"),
        _provider(json.dumps({"decision": "teleport"})),
    ],
    ids=["llm-error", "bad-json", "unknown-decision"],
)
async def test_llm_failure_falls_back_to_existing_workflow(task, provider, caplog):
    props = _continuation_props()
    context = _context(props, _Library(["Brainstorm Ideas"]))

    result, _ = await _run(task, context, provider)

    assert result.success
    assert result.next_route == "existing_workflow"
    assert props["continuation_decision"] == "existing_workflow"
    assert "defaulting to workflow selection" in props["continuation_rationale"]
    assert "Continuation assessment failed" in caplog.text


async def test_missing_provider_falls_back(task):
    props = _continuation_props()
    context = _context(props, _Library(["Brainstorm Ideas"]))
    with patch(
        "zebra_tasks.agent.continuation_assessor.get_provider",
        side_effect=ValueError("Unknown LLM provider"),
    ):
        result = await ContinuationAssessorAction().run(task, context)

    assert result.next_route == "existing_workflow"


async def test_model_resolved_from_process_property(task):
    props = _continuation_props(__llm_model__="haiku")
    context = _context(props, _Library(["Brainstorm Ideas"]))
    content = json.dumps({"decision": "existing_workflow", "rationale": "x"})

    _, get_provider = await _run(task, context, _provider(content))

    get_provider.assert_called_once_with("anthropic", "haiku")
