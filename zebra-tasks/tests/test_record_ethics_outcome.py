"""Tests for RecordEthicsReviewAction and RecordEthicsRejectionAction (#143)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from zebra_tasks.agent.record_ethics_rejection import RecordEthicsRejectionAction
from zebra_tasks.agent.record_ethics_review import RecordEthicsReviewAction


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
    context.process.properties = {"__user_id__": 42, "goal": "Write a poem"}
    context.extras = {}
    context.set_process_property = MagicMock(
        side_effect=lambda k, v: context.process.properties.__setitem__(k, v)
    )
    context.get_process_property = MagicMock(
        side_effect=lambda k, d=None: context.process.properties.get(k, d)
    )
    return context


@pytest.fixture
def audit(mock_context):
    store = MagicMock()
    store.append = AsyncMock()
    mock_context.extras["__ethics_audit_store__"] = store
    return store


class TestRecordEthicsReview:
    async def test_ethical_review_is_normalised_and_audited(self, mock_task, mock_context, audit):
        mock_context.process.properties["ethics_post_assessment"] = {
            "ethical": True,
            "overall_reasoning": "fine",
            "concerns": ["minor"],
            "recommendations": ["cite sources"],
            "autonomy": {"pass": True},
        }

        result = await RecordEthicsReviewAction().run(mock_task, mock_context)

        assert result.success
        assert result.output == {
            "ethical": True,
            "overall_reasoning": "fine",
            "concerns": ["minor"],
            "recommendations": ["cite sources"],
        }
        assert mock_context.process.properties["ethics_post_assessment"] == result.output
        entry = audit.append.await_args.args[0]
        assert entry.check_type == "post_review"
        assert entry.approved is True
        assert entry.overall_reasoning == "fine"
        assert entry.goal == "Write a poem"
        assert entry.user_id == 42
        assert entry.process_id == "process-1"

    async def test_unparseable_review_fails_closed(self, mock_task, mock_context, audit):
        mock_context.process.properties["ethics_post_assessment"] = "not json at all"

        result = await RecordEthicsReviewAction().run(mock_task, mock_context)

        assert result.success
        assert result.output["ethical"] is False
        assert "could not be parsed" in result.output["overall_reasoning"]
        entry = audit.append.await_args.args[0]
        assert entry.approved is False

    async def test_missing_audit_store_still_succeeds(self, mock_task, mock_context):
        mock_context.process.properties["ethics_post_assessment"] = {"ethical": True}

        result = await RecordEthicsReviewAction().run(mock_task, mock_context)

        assert result.success
        assert result.output["ethical"] is True

    async def test_audit_failure_does_not_fail_action(self, mock_task, mock_context, audit):
        audit.append.side_effect = RuntimeError("db down")
        mock_context.process.properties["ethics_post_assessment"] = {"ethical": False}

        result = await RecordEthicsReviewAction().run(mock_task, mock_context)

        assert result.success
        assert result.output["ethical"] is False


class TestRecordEthicsRejection:
    async def _run(self, mock_task, mock_context, **props):
        mock_context.process.properties.update(props)
        return await RecordEthicsRejectionAction().run(mock_task, mock_context)

    async def test_input_gate_rejection(self, mock_task, mock_context):
        result = await self._run(
            mock_task,
            mock_context,
            ethics_input_assessment={
                "approved": False,
                "overall_reasoning": "Rejected on ethical grounds",
                "concerns": ["Deception"],
            },
        )

        assert result.success
        assert result.output == {
            "gate": "input_gate",
            "reasoning": "Rejected on ethical grounds",
            "concerns": ["Deception"],
        }
        assert mock_context.process.properties["ethics_rejection"] == result.output

    async def test_plan_review_rejection(self, mock_task, mock_context):
        result = await self._run(
            mock_task,
            mock_context,
            ethics_input_assessment={"approved": True, "overall_reasoning": "OK"},
            ethics_plan_assessment={
                "approved": False,
                "overall_reasoning": "Plan is unethical",
                "concerns": ["Exploits resources"],
            },
        )

        assert result.output["gate"] == "plan_review"
        assert result.output["reasoning"] == "Plan is unethical"
        assert result.output["concerns"] == ["Exploits resources"]

    async def test_declined_dilemma(self, mock_task, mock_context):
        result = await self._run(
            mock_task,
            mock_context,
            ethics_input_assessment={"approved": True},
            # Escalated plan reviews are approved=True — the human made the call.
            ethics_plan_assessment={"approved": True, "concerns": ["candour vs kindness"]},
            dilemma_resolution={"decision": "decline", "note": "not worth it", "route": "reject"},
        )

        assert result.output["gate"] == "dilemma_resolution"
        assert "not worth it" in result.output["reasoning"]
        assert result.output["concerns"] == ["candour vs kindness"]

    async def test_missing_assessments_still_records(self, mock_task, mock_context):
        result = await self._run(mock_task, mock_context)

        assert result.success
        assert result.output == {"gate": "input_gate", "reasoning": "", "concerns": []}
