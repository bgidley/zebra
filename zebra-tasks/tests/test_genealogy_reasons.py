"""Writers pass only the reason they recorded to the lineage journal (#238)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from zebra_agent.genealogy import LineageJournal
from zebra_agent.library import WorkflowLibrary

from zebra_tasks.agent.creator import WorkflowCreatorAction, selection_reason
from zebra_tasks.agent.optimizer import WorkflowOptimizerAction, evaluator_reason
from zebra_tasks.agent.variant_creator import WorkflowVariantCreatorAction
from zebra_tasks.llm.base import LLMResponse, TokenUsage
from zebra_tasks.llm.client import set_llm_factory


def _workflow(prompt: str, name: str = "Project Update") -> str:
    return f"""name: "{name}"
description: "Update a project plan"
version: 1
first_task: step1
tasks:
  step1:
    name: "Step"
    action: llm_call
    auto: true
    properties:
      prompt: "{prompt}"
"""


ORIGINAL = _workflow("Update the plan: {{goal}}")
IMPROVED = _workflow("Update the plan step by step: {{goal}}")


def _provider(*contents: str) -> None:
    provider = MagicMock()
    provider.complete = AsyncMock(
        side_effect=[
            LLMResponse(
                content=c,
                tool_calls=None,
                finish_reason="end_turn",
                usage=TokenUsage(input_tokens=1, output_tokens=1),
                model="test",
            )
            for c in contents
        ]
    )
    set_llm_factory(lambda model: provider)


@pytest.fixture
def library(tmp_path):
    lib = WorkflowLibrary(tmp_path / "wf", owner_user_id=1, sphere="home")
    lib.add_workflow(ORIGINAL)
    return lib


@pytest.fixture
def context(library):
    ctx = MagicMock()
    ctx.process.id = "p1"
    ctx.process.properties = {"__user_id__": 1}
    ctx.extras = {"__workflow_library__": library}
    ctx.get_process_property = MagicMock(
        side_effect=lambda k, d=None: ctx.process.properties.get(k, d)
    )
    ctx.set_process_property = MagicMock(
        side_effect=lambda k, v: ctx.process.properties.__setitem__(k, v)
    )
    ctx.resolve_template = MagicMock(side_effect=lambda x: x)
    ctx.engine.actions.format_for_prompt = MagicMock(return_value="## Actions\n- llm_call\n")
    ctx.engine.actions.has_action = MagicMock(side_effect=lambda name: name == "llm_call")
    return ctx


def _last(library) -> dict:
    return LineageJournal(library.library_path).read()[-1]


async def test_optimizer_records_the_priority_rationale(library, context):
    _provider(IMPROVED)
    task = MagicMock()
    task.properties = {
        "evaluation": {
            "improvement_priorities": [
                {
                    "type": "fix",
                    "target": "Project Update",
                    "action": "add steps",
                    "rationale": "three failed runs at work",
                }
            ],
            "new_workflow_suggestions": [],
            "workflow_evaluations": [],
            "run_exposure": [],
        },
        "existing_workflows": {"Project Update": ORIGINAL},
        "dry_run": False,
        "workflow_library_path": str(library.library_path),
    }
    result = await WorkflowOptimizerAction().run(task, context)

    assert result.success and result.output["changes_made"]
    record = _last(library)
    assert record["writer"] == "optimizer"
    assert record["reason"] == {
        "text": "three failed runs at work",
        "kind": "reasoning",
        "source": "evaluator",
    }


async def test_creator_records_the_selector_voice(library, context):
    context.process.properties["selection"] = {
        "reasoning": "No workflow writes cover letters.",
        "voice": "I have nothing for cover letters yet, so I'll write one.",
    }
    _provider(_workflow("Write a cover letter: {{goal}}", name="Cover Letter"))
    task = MagicMock()
    task.properties = {"goal": "Write a cover letter", "output_key": "created_workflow"}
    result = await WorkflowCreatorAction().run(task, context)

    assert result.success
    record = _last(library)
    assert record["writer"] == "creator" and record["name"] == "Cover Letter"
    assert record["reason"] == {
        "text": "I have nothing for cover letters yet, so I'll write one.",
        "kind": "voice",
        "source": "selector",
    }


async def test_variant_creator_falls_back_to_recorded_reasoning(library, context):
    context.process.properties["selection"] = {"reasoning": "Close, but needs detail."}
    _provider(_workflow("Update the plan in detail: {{goal}}", name="Detailed Update"))
    task = MagicMock()
    task.properties = {"goal": "Detailed plan", "source_workflow_name": "Project Update"}
    result = await WorkflowVariantCreatorAction().run(task, context)

    assert result.success
    record = _last(library)
    assert record["writer"] == "variant_creator" and record["parent_name"] == "Project Update"
    assert record["reason"]["kind"] == "reasoning"
    assert record["reason"]["text"] == "Close, but needs detail."


def test_no_recorded_reason_means_none(context):
    assert selection_reason(context) is None
    context.process.properties["selection"] = {"reasoning": "  ", "voice": None}
    assert selection_reason(context) is None
    assert evaluator_reason("") is None and evaluator_reason(None) is None
