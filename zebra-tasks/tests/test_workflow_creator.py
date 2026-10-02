"""Tests for WorkflowCreatorAction guarding against truncated / broken generated workflows."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zebra_tasks.agent.creator import GENERATED_WORKFLOW_MAX_TOKENS, WorkflowCreatorAction
from zebra_tasks.llm.base import LLMResponse, TokenUsage

_VALID_YAML = """name: FIRE Calculator
description: Gather data then calculate
first_task: gather
tasks:
  gather:
    name: Gather Info
    auto: false
    properties:
      schema:
        type: object
        properties:
          savings:
            type: number
  calculate:
    name: Calculate
    action: llm_call
    properties:
      prompt: "{{gather.output}}"
routings:
  - from: gather
    to: calculate
"""

# Same workflow with the routings block cut off, as happens when max_tokens is hit.
_TRUNCATED_YAML = _VALID_YAML.split("routings:")[0]


def _response(content: str, finish_reason: str = "end_turn") -> LLMResponse:
    return LLMResponse(
        content=content,
        tool_calls=None,
        finish_reason=finish_reason,
        usage=TokenUsage(input_tokens=10, output_tokens=20),
        model="test-model",
    )


@pytest.fixture
def task():
    task = MagicMock()
    task.properties = {"goal": "Can I retire early?"}
    return task


@pytest.fixture
def context():
    context = MagicMock()
    context.process.properties = {}
    context.extras = {}
    context.get_process_property = MagicMock(
        side_effect=lambda k, d=None: context.process.properties.get(k, d)
    )
    context.set_process_property = MagicMock(
        side_effect=lambda k, v: context.process.properties.__setitem__(k, v)
    )
    context.resolve_template = MagicMock(side_effect=lambda x: x)
    context.engine.actions.format_for_prompt = MagicMock(return_value="")
    return context


async def _run(task, context, response: LLMResponse):
    provider = MagicMock()
    provider.complete = AsyncMock(return_value=response)
    with patch("zebra_tasks.agent.creator.get_provider", return_value=provider):
        result = await WorkflowCreatorAction().run(task, context)
    return result, provider


async def test_valid_workflow_is_accepted(task, context):
    library = MagicMock()
    context.extras["__workflow_library__"] = library

    result, provider = await _run(task, context, _response(_VALID_YAML))

    assert result.success is True
    assert context.process.properties["workflow_name"] == "FIRE Calculator"
    library.add_workflow.assert_called_once()
    assert provider.complete.call_args.kwargs["max_tokens"] == GENERATED_WORKFLOW_MAX_TOKENS


@pytest.mark.parametrize("finish_reason", ["max_tokens", "length"])
async def test_truncated_output_is_rejected(task, context, finish_reason):
    library = MagicMock()
    context.extras["__workflow_library__"] = library

    result, _ = await _run(task, context, _response(_VALID_YAML, finish_reason))

    assert result.success is False
    assert "truncated" in result.error
    library.add_workflow.assert_not_called()


async def test_orphaned_tasks_are_rejected(task, context):
    library = MagicMock()
    context.extras["__workflow_library__"] = library

    result, _ = await _run(task, context, _response(_TRUNCATED_YAML))

    assert result.success is False
    assert "'calculate' has no incoming routes" in result.error
    library.add_workflow.assert_not_called()
    assert "workflow_name" not in context.process.properties
