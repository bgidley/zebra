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


async def test_invalid_workflow_is_repaired_once(task, context):
    library = MagicMock()
    context.extras["__workflow_library__"] = library
    provider = MagicMock()
    provider.complete = AsyncMock(side_effect=[_response(_TRUNCATED_YAML), _response(_VALID_YAML)])

    with patch("zebra_tasks.agent.creator.get_provider", return_value=provider):
        result = await WorkflowCreatorAction().run(task, context)

    assert result.success is True
    assert provider.complete.call_count == 2
    repair_messages = provider.complete.call_args_list[1].kwargs["messages"]
    assert repair_messages[-2].content == _TRUNCATED_YAML.strip()
    assert "'calculate' has no incoming routes" in repair_messages[-1].content
    library.add_workflow.assert_called_once_with(_VALID_YAML.strip())


async def test_failed_repair_makes_exactly_two_calls(task, context):
    _, provider = await _run(task, context, _response(_TRUNCATED_YAML))

    assert provider.complete.call_count == 2


async def test_unparseable_yaml_is_repaired(task, context):
    provider = MagicMock()
    provider.complete = AsyncMock(
        side_effect=[_response("name: [unclosed"), _response(_VALID_YAML)]
    )

    with patch("zebra_tasks.agent.creator.get_provider", return_value=provider):
        result = await WorkflowCreatorAction().run(task, context)

    assert result.success is True
    assert "YAML did not load" in provider.complete.call_args_list[1].kwargs["messages"][-1].content


async def test_truncated_output_is_not_repaired(task, context):
    _, provider = await _run(task, context, _response(_VALID_YAML, "max_tokens"))

    assert provider.complete.call_count == 1


async def test_system_prompt_describes_engine_semantics(task, context):
    _, provider = await _run(task, context, _response(_VALID_YAML))

    system_prompt = provider.complete.call_args.kwargs["messages"][0].content
    for phrase in (
        "{{__task_output_<task_id>.<field>}}",
        "parallel: true",
        "synchronized: true",
        "shown to the user as a button",
        "file_delete",
    ):
        assert phrase in system_prompt
    assert "use an enum field and conditional routings" not in system_prompt
    assert provider.complete.call_args.kwargs["temperature"] == 0.3


async def test_route_name_after_llm_call_is_rejected(task, context):
    bad_yaml = _VALID_YAML.replace(
        "routings:\n  - from: gather\n    to: calculate\n",
        "  done:\n    name: Done\n    action: llm_call\n    properties:\n      prompt: x\n"
        "routings:\n  - from: gather\n    to: calculate\n"
        "  - from: calculate\n    to: done\n    condition: route_name\n    name: ok\n",
    )

    result, _ = await _run(task, context, _response(bad_yaml))

    assert result.success is False
    assert "llm_call tasks never choose a route" in result.error


def test_prompt_template_forms_resolve():
    """The Data Flow forms the prompt teaches must resolve with the real resolver."""
    from zebra.tasks.base import ExecutionContext

    process = MagicMock()
    process.properties = {
        # As kagi_search stores them: main value under output_key, full output separately.
        "search_results": [{"url": "https://a.example"}],
        "__task_output_search": {"results": [{"url": "https://a.example"}], "total": 1},
        "__task_output_get_input": {"description": "broken login"},
    }
    ctx = ExecutionContext(
        engine=None, store=None, process=process, process_definition=None, task_definition=None
    )

    assert "https://a.example" in ctx.resolve_template("{{search_results}}")
    assert ctx.resolve_template("{{__task_output_search.total}}") == "1"
    assert ctx.resolve_template("{{__task_output_get_input.description}}") == "broken login"
    assert "broken login" in ctx.resolve_template("{{get_input.output}}")
