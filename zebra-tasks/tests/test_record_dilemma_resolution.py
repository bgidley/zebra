"""Tests for RecordDilemmaResolutionAction (F22 / REQ-ETH-005)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from zebra_tasks.agent.record_dilemma_resolution import RecordDilemmaResolutionAction


@pytest.fixture
def mock_task():
    task = MagicMock()
    task.id = "task-1"
    task.process_id = "process-1"
    task.properties = {}
    return task


@pytest.fixture
def mock_context():
    context = MagicMock()
    context.process = MagicMock()
    context.process.properties = {"__user_id__": 42}
    context.extras = {}
    context._task_outputs = {}
    context.set_process_property = MagicMock(
        side_effect=lambda k, v: context.process.properties.__setitem__(k, v)
    )
    context.get_process_property = MagicMock(
        side_effect=lambda k, d=None: context.process.properties.get(k, d)
    )
    context.get_task_output = MagicMock(side_effect=lambda t: context._task_outputs.get(t))
    context.resolve_template = MagicMock(side_effect=lambda x: x)
    return context


class TestRecordDilemmaResolution:
    async def test_proceed_routes_proceed_and_audits(self, mock_task, mock_context):
        audit = MagicMock()
        audit.append = AsyncMock()
        mock_context.extras["__ethics_audit_store__"] = audit
        mock_context._task_outputs["ethics_dilemma_resolution"] = {
            "decision": "proceed",
            "note": "I value candour",
        }
        mock_task.properties = {"goal": "Give feedback"}

        action = RecordDilemmaResolutionAction()
        result = await action.run(mock_task, mock_context)

        assert result.next_route == "proceed"
        assert result.output["decision"] == "proceed"
        assert mock_context.process.properties["dilemma_resolution"]["decision"] == "proceed"
        audit.append.assert_awaited_once()
        entry = audit.append.await_args.args[0]
        assert entry.check_type == "dilemma_resolution"
        assert entry.approved is True
        assert entry.user_id == 42

    async def test_decline_routes_reject(self, mock_task, mock_context):
        mock_context._task_outputs["ethics_dilemma_resolution"] = {"decision": "decline"}

        action = RecordDilemmaResolutionAction()
        result = await action.run(mock_task, mock_context)

        assert result.next_route == "reject"
        assert result.output["decision"] == "decline"

    async def test_degrades_without_audit_store(self, mock_task, mock_context):
        """No audit store → still records on process and routes correctly."""
        mock_context._task_outputs["ethics_dilemma_resolution"] = {"decision": "proceed"}

        action = RecordDilemmaResolutionAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.next_route == "proceed"

    async def test_missing_human_output_defaults_proceed(self, mock_task, mock_context):
        """If the human task output is absent, default to proceed (fail open, not stuck)."""
        action = RecordDilemmaResolutionAction()
        result = await action.run(mock_task, mock_context)

        assert result.next_route == "proceed"
