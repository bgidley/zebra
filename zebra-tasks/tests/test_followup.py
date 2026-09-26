"""Tests for follow-up goal support (F116)."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from zebra_tasks.agent.ethics_gate import EthicsGateAction
from zebra_tasks.agent.execute_workflow import ExecuteGoalWorkflowAction
from zebra_tasks.agent.followup import (
    MAX_PREVIOUS_OUTPUT_CHARS,
    build_previous_run_context,
    previous_run_id,
    with_previous_run,
)

PREVIOUS = {
    "run_id": "run-1",
    "goal": "Summarise the Q3 report",
    "workflow_name": "Summariser",
    "success": True,
    "output": "Revenue grew 12%.",
}


def _run(**overrides):
    fields = {
        "id": "run-1",
        "goal": "Summarise the Q3 report",
        "workflow_name": "Summariser",
        "output": "Revenue grew 12%.",
        "success": True,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _context(properties: dict) -> MagicMock:
    context = MagicMock()
    context.process.id = "process-1"
    context.process.properties = properties
    context.extras = {}
    context.resolve_template = MagicMock(side_effect=lambda x: x)
    return context


# --- helpers -----------------------------------------------------------------


def test_with_previous_run_returns_goal_unchanged_without_context():
    assert with_previous_run("Do the thing", {}) == "Do the thing"


def test_with_previous_run_appends_previous_goal_workflow_and_output():
    text = with_previous_run("Now make it shorter", {"previous_run_context": PREVIOUS})

    assert text.startswith("Now make it shorter")
    assert "Previous goal: Summarise the Q3 report" in text
    assert "Workflow used: Summariser" in text
    assert "Outcome: succeeded" in text
    assert "Revenue grew 12%." in text


def test_with_previous_run_flags_failed_previous_run():
    ctx = {**PREVIOUS, "success": False}

    assert "Outcome: failed" in with_previous_run("Retry", {"previous_run_context": ctx})


def test_build_previous_run_context_serialises_and_truncates_output():
    run = _run(output={"text": "x" * (MAX_PREVIOUS_OUTPUT_CHARS * 2)}, success=False)

    ctx = build_previous_run_context(run)

    assert ctx["run_id"] == "run-1"
    assert ctx["success"] is False
    assert len(ctx["output"]) == MAX_PREVIOUS_OUTPUT_CHARS
    assert ctx["output"].startswith('{"text": "xxx')
    json.dumps(ctx)  # must be JSON-serializable for process properties


def test_build_previous_run_context_handles_missing_output():
    assert build_previous_run_context(_run(output=None))["output"] == ""


def test_chained_follow_ups_do_not_nest_previous_run_blocks():
    """A follow-up of a follow-up carries only its direct predecessor's context."""
    first_props = {"goal": "Make it shorter", "previous_run_context": PREVIOUS}
    with_previous_run(first_props["goal"], first_props)
    assert first_props["goal"] == "Make it shorter"  # annotation never mutates the goal

    # The follow-up run is recorded with its plain goal, then extended again
    follow_up_run = _run(id="run-2", goal=first_props["goal"], output="Revenue up 12%.")
    second_props = {"previous_run_context": build_previous_run_context(follow_up_run)}

    text = with_previous_run("Now translate it", second_props)

    assert text.count("<previous_run>") == 1
    assert "Previous goal: Make it shorter" in text
    assert "Summarise the Q3 report" not in text


def test_previous_run_id():
    assert previous_run_id({"previous_run_context": PREVIOUS}) == "run-1"
    assert previous_run_id({}) is None


# --- actions -----------------------------------------------------------------


async def test_executed_workflow_receives_previous_run_context():
    """The workflow that does the work must see the previous run, not just the selector."""
    context = _context({"previous_run_context": PREVIOUS})
    captured = {}

    async def create_process(definition, properties):
        captured.update(properties)
        raise RuntimeError("stop after capture")

    context.engine.create_process = create_process
    library = MagicMock()
    library.get_workflow.return_value = MagicMock()
    task = MagicMock()
    task.properties = {"workflow_name": "Summariser", "goal": "Now make it shorter"}

    await ExecuteGoalWorkflowAction(workflow_library=library).run(task, context)

    assert captured["goal"].startswith("Now make it shorter")
    assert "Revenue grew 12%." in captured["goal"]


async def test_executed_workflow_goal_unchanged_without_previous_run():
    context = _context({})
    captured = {}

    async def create_process(definition, properties):
        captured.update(properties)
        raise RuntimeError("stop after capture")

    context.engine.create_process = create_process
    library = MagicMock()
    task = MagicMock()
    task.properties = {"workflow_name": "Summariser", "goal": "Plain goal"}

    await ExecuteGoalWorkflowAction(workflow_library=library).run(task, context)

    assert captured["goal"] == "Plain goal"


async def test_ethics_input_gate_judges_goal_with_previous_run():
    context = _context({"previous_run_context": PREVIOUS})
    provider = MagicMock()
    provider.complete = AsyncMock(
        return_value=MagicMock(
            content=json.dumps(
                {
                    "approved": True,
                    "universalizability": {"pass": True, "reasoning": "ok"},
                    "rational_beings_as_ends": {"pass": True, "reasoning": "ok"},
                    "autonomy": {"pass": True, "reasoning": "ok"},
                    "overall_reasoning": "fine",
                    "concerns": [],
                }
            ),
            usage=MagicMock(input_tokens=1, output_tokens=1, total_tokens=2),
        )
    )
    task = MagicMock()
    task.id = "task-1"
    task.properties = {"goal": "Now make it shorter", "check_type": "input_gate"}

    with patch("zebra_tasks.agent.ethics_gate.get_provider", return_value=provider):
        result = await EthicsGateAction().run(task, context)

    assert result.success is True
    messages = (
        provider.complete.call_args.kwargs.get("messages") or (provider.complete.call_args.args[0])
    )
    user_prompt = messages[-1].content
    assert "Now make it shorter" in user_prompt
    assert "Summarise the Q3 report" in user_prompt
