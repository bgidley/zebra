"""Tests for Zebra's voice fields on reasoning outputs (#161)."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from zebra_tasks.agent import (
    continuation_assessor,
    ethics_gate,
    flag_concerns,
    selector,
)
from zebra_tasks.agent.continuation_assessor import ContinuationAssessorAction
from zebra_tasks.agent.ethics_gate import EthicsGateAction
from zebra_tasks.agent.flag_concerns import FlagConcernsAction
from zebra_tasks.agent.record_ethics_review import normalise_post_review
from zebra_tasks.agent.selector import WorkflowSelectorAction
from zebra_tasks.agent.voice import VOICE_MAX_CHARS, extract_voice, voice_fields

MAIN_LOOP = (
    Path(__file__).resolve().parents[2] / "zebra-agent" / "workflows" / "agent_main_loop.yaml"
)

VOICE = {"voice": "I'd rather ask before publishing anything you can't undo.", "confidence": 0.62}


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


def test_extract_voice_keeps_text_and_clamps_confidence():
    assert extract_voice({"voice": "  I chose  the\nresearch flow. ", "confidence": 1.7}) == {
        "voice": "I chose the research flow.",
        "confidence": 1.0,
    }
    assert extract_voice({"voice": "ok", "confidence": -0.2})["confidence"] == 0.0
    assert extract_voice({"voice": "ok", "confidence": "0.456"})["confidence"] == 0.46


@pytest.mark.parametrize(
    "data",
    [
        None,
        "not a dict",
        {},
        {"voice": "", "confidence": None},
        {"voice": 42, "confidence": True},
        {"voice": None, "confidence": "high"},
    ],
)
def test_extract_voice_rejects_missing_or_invalid_values(data):
    assert extract_voice(data) == {"voice": None, "confidence": None}


def test_extract_voice_clips_long_text():
    voice = extract_voice({"voice": "word " * 200})["voice"]

    assert len(voice) == VOICE_MAX_CHARS
    assert voice.endswith("…")


def test_zero_confidence_is_kept_not_treated_as_missing():
    assert extract_voice({"voice": "I'm unsure.", "confidence": 0})["confidence"] == 0.0
    assert voice_fields({"confidence": 0.0}) == {"confidence": 0.0}


def test_voice_fields_only_returns_supplied_values():
    assert voice_fields({"voice": "I agree."}) == {"voice": "I agree."}
    assert voice_fields({"confidence": 0.5}) == {"confidence": 0.5}
    assert voice_fields({}) == {}


# ---------------------------------------------------------------------------
# Prompts ask for the voice fields
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prompt",
    [
        ethics_gate.KANTIAN_SYSTEM_PROMPT,
        ethics_gate._COMBINED_JSON_SCHEMA,
        flag_concerns.SYSTEM_PROMPT,
        continuation_assessor.SYSTEM_PROMPT,
        selector.WorkflowSelectorAction.SYSTEM_PROMPT,
    ],
)
def test_reasoning_prompts_request_voice_and_confidence(prompt):
    assert '"voice":' in prompt
    assert '"confidence":' in prompt
    assert "first person" in prompt


def test_post_review_prompt_requests_voice_and_version_is_bumped():
    workflow = yaml.safe_load(MAIN_LOOP.read_text())
    prompt = workflow["tasks"]["ethics_post_review"]["properties"]["system_prompt"]

    assert '"voice":' in prompt and '"confidence":' in prompt
    # Built-in workflows only reach the live library on a version bump.
    assert workflow["version"] >= 15


# ---------------------------------------------------------------------------
# Producers store the voice
# ---------------------------------------------------------------------------


def _context(properties=None, extras=None):
    context = MagicMock()
    context.process = MagicMock()
    context.process.id = "process-1"
    context.process.properties = properties if properties is not None else {}
    context.extras = extras or {}
    context.set_process_property = MagicMock(
        side_effect=lambda k, v: context.process.properties.__setitem__(k, v)
    )
    context.resolve_template = MagicMock(side_effect=lambda x: x)
    return context


def _task(**properties):
    task = MagicMock()
    task.id = "task-1"
    task.process_id = "process-1"
    task.properties = properties
    return task


def _provider(payload) -> MagicMock:
    response = MagicMock()
    response.content = json.dumps(payload)
    provider = MagicMock()
    provider.complete = AsyncMock(return_value=response)
    return provider


_ETHICS_OK = {
    "approved": True,
    "universalizability": {"pass": True, "reasoning": "fine"},
    "rational_beings_as_ends": {"pass": True, "reasoning": "fine"},
    "autonomy": {"pass": True, "reasoning": "fine"},
    "overall_reasoning": "Sound.",
    "concerns": [],
}


async def test_ethics_gate_stores_voice():
    context = _context()
    task = _task(goal="Write a poem", check_type="input_gate", output_key="ethics_input_assessment")

    with patch.object(ethics_gate, "get_llm", return_value=_provider({**_ETHICS_OK, **VOICE})):
        result = await EthicsGateAction().run(task, context)

    stored = context.process.properties["ethics_input_assessment"]
    assert stored["voice"] == VOICE["voice"]
    assert stored["confidence"] == 0.62
    assert result.output["voice"] == VOICE["voice"]


async def test_ethics_gate_drops_invalid_raw_voice():
    context = _context()
    task = _task(goal="Write a poem", check_type="input_gate", output_key="ethics_input_assessment")
    raw = {**_ETHICS_OK, "voice": 7, "confidence": "very"}

    with patch.object(ethics_gate, "get_llm", return_value=_provider(raw)):
        await EthicsGateAction().run(task, context)

    stored = context.process.properties["ethics_input_assessment"]
    assert "voice" not in stored and "confidence" not in stored


async def test_flag_concerns_stores_voice():
    context = _context()
    task = _task(goal="Publish the digest", plan_context="Weekly Digest")
    payload = {"concerns": [], "summary": "Low risk.", **VOICE}

    with patch.object(flag_concerns, "get_llm", return_value=_provider(payload)):
        result = await FlagConcernsAction().run(task, context)

    assert result.output == {"concerns": [], "summary": "Low risk.", **VOICE}
    assert context.process.properties["planning_concerns"]["voice"] == VOICE["voice"]


async def test_selector_stores_voice_only_when_given():
    workflows = [{"name": "Web Research", "description": "Search the web", "tags": []}]
    task = _task(
        goal="Compare passkey libraries",
        available_workflows=json.dumps(workflows),
        output_key="selection",
    )
    pick = {
        "workflow_name": "Web Research",
        "create_new": False,
        "create_variant": False,
        "reasoning": "Needs fresh sources.",
    }

    context = _context()
    with patch.object(selector, "get_llm", return_value=_provider({**pick, **VOICE})):
        await WorkflowSelectorAction().run(task, context)
    assert context.process.properties["selection"]["voice"] == VOICE["voice"]
    assert context.process.properties["selection"]["confidence"] == 0.62

    context = _context()
    with patch.object(selector, "get_llm", return_value=_provider(pick)):
        await WorkflowSelectorAction().run(task, context)
    assert "voice" not in context.process.properties["selection"]


async def test_continuation_stores_voice():
    previous = {
        "run_id": "run-1",
        "goal": "Research bikes",
        "workflow_name": "Brainstorm Ideas",
        "success": False,
        "output": "Partial",
    }
    props = {"previous_run_context": previous}
    context = _context(props)
    task = _task(goal="Finish it", output_key="continuation_assessment")
    payload = {"decision": "existing_workflow", "rationale": "Different job now.", **VOICE}

    with patch.object(continuation_assessor, "get_llm", return_value=_provider(payload)):
        result = await ContinuationAssessorAction().run(task, context)

    assert result.output["voice"] == VOICE["voice"]
    assert props["continuation_assessment"]["confidence"] == 0.62


def test_post_review_normaliser_keeps_voice():
    review = normalise_post_review({"ethical": True, "overall_reasoning": "Fine.", **VOICE})

    assert review["voice"] == VOICE["voice"]
    assert review["confidence"] == 0.62
    assert "voice" not in normalise_post_review({"ethical": True})
