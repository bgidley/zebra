"""Tests for the shared queue_goal() helper (F34 / REQ-UI-003).

Verifies the extracted helper builds the same process properties the
run_goal_queue view assembled before the refactor, so CLI-queued and
web-queued goals are indistinguishable.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_workflow(name: str, use_count: int = 0, tags: list | None = None):
    wf = MagicMock()
    wf.name = name
    wf.description = f"{name} description"
    wf.tags = tags or []
    wf.success_rate = 0.5
    wf.use_count = use_count
    wf.use_when = f"use {name}"
    return wf


@pytest.fixture
def mock_machinery():
    """Patch agent_engine/engine/get_engine used inside queue_goal."""
    definition = MagicMock()
    created_process = MagicMock()
    created_process.id = "proc-12345678"

    library = MagicMock()
    library.get_workflow.return_value = definition
    library.list_workflows = AsyncMock(
        return_value=[
            _make_workflow("Answer Question", use_count=3),
            _make_workflow("Agent Main Loop", tags=["system"]),
        ]
    )

    wf_engine = MagicMock()
    wf_engine.create_process = AsyncMock(return_value=created_process)

    with (
        patch("zebra_agent_web.api.agent_engine.ensure_initialized", new=AsyncMock()),
        patch("zebra_agent_web.api.engine.ensure_initialized", new=AsyncMock()),
        patch("zebra_agent_web.api.agent_engine.get_library", return_value=library),
        patch("zebra_agent_web.api.engine.get_engine", return_value=wf_engine),
    ):
        yield {
            "library": library,
            "wf_engine": wf_engine,
            "definition": definition,
            "process": created_process,
        }


async def test_queue_goal_builds_pre_refactor_properties(mock_machinery):
    """Properties dict matches the shape the view assembled before extraction."""
    from zebra_agent_web.api.goals import queue_goal

    process = await queue_goal(
        "Write a report",
        model="haiku",
        priority=2,
        deadline="2026-07-01T12:00:00Z",
        user_id=42,
        identity={"user_display_name": "Ben", "user_identity_id": "id-1"},
    )

    assert process is mock_machinery["process"]
    call = mock_machinery["wf_engine"].create_process.call_args
    assert call.args[0] is mock_machinery["definition"]
    props = call.kwargs["properties"]

    assert props["goal"] == "Write a report"
    assert props["priority"] == 2
    assert props["run_id"]
    assert props["deadline"] == "2026-07-01T12:00:00Z"
    assert props["__llm_provider_name__"] == "anthropic"
    # haiku alias resolved to a full model id
    assert props["__llm_model__"] and props["__llm_model__"] != "haiku"
    assert props["__user_id__"] == 42
    assert props["__user_display_name__"] == "Ben"
    assert props["__user_identity_id__"] == "id-1"
    assert props["__started_at__"]
    # system workflows excluded from available list
    names = [w["name"] for w in props["available_workflows"]]
    assert "Answer Question" in names
    assert "Agent Main Loop" not in names


async def test_queue_goal_defaults(mock_machinery):
    """No model/identity/deadline: sensible defaults, no deadline key."""
    from zebra_agent_web.api.goals import queue_goal

    await queue_goal("Do something")

    props = mock_machinery["wf_engine"].create_process.call_args.kwargs["properties"]
    assert props["priority"] == 3
    assert props["__llm_model__"] is None
    assert props["__user_id__"] is None
    assert props["__user_display_name__"] == ""
    assert "deadline" not in props


async def test_queue_goal_clamps_priority(mock_machinery):
    """Priority is clamped to 1-5."""
    from zebra_agent_web.api.goals import queue_goal

    await queue_goal("Do something", priority=99)
    props = mock_machinery["wf_engine"].create_process.call_args.kwargs["properties"]
    assert props["priority"] == 5


async def test_queue_goal_rejects_empty_goal(mock_machinery):
    """Empty goal raises ValueError."""
    from zebra_agent_web.api.goals import queue_goal

    with pytest.raises(ValueError, match="Goal is required"):
        await queue_goal("   ")
