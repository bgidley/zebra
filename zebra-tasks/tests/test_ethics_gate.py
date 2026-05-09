"""Tests for EthicsGateAction - Kantian categorical imperative evaluation."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zebra_tasks.agent.ethics_gate import EthicsGateAction


@pytest.fixture
def mock_task():
    """Create a mock task instance."""
    task = MagicMock()
    task.id = "task-1"
    task.properties = {}
    return task


@pytest.fixture
def mock_context():
    """Create a mock execution context."""
    context = MagicMock()
    context.process = MagicMock()
    context.process.id = "process-1"
    context.process.properties = {}
    context.extras = {}
    context.set_process_property = MagicMock(
        side_effect=lambda k, v: context.process.properties.__setitem__(k, v)
    )
    context.resolve_template = MagicMock(side_effect=lambda x: x)
    return context


def _make_provider(response_json: dict) -> MagicMock:
    """Create a mock LLM provider that returns the given JSON."""
    provider = MagicMock()
    provider.complete = AsyncMock(
        return_value=MagicMock(
            content=json.dumps(response_json),
            model="test-model",
            usage=MagicMock(input_tokens=100, output_tokens=50, total_tokens=150),
        )
    )
    return provider


def _approved_response() -> dict:
    return {
        "approved": True,
        "universalizability": {"pass": True, "reasoning": "Can be universalized."},
        "rational_beings_as_ends": {"pass": True, "reasoning": "Respects all beings."},
        "autonomy": {"pass": True, "reasoning": "Preserves autonomy."},
        "overall_reasoning": "This goal is ethically sound.",
        "concerns": [],
    }


def _rejected_response() -> dict:
    return {
        "approved": False,
        "universalizability": {"pass": False, "reasoning": "Cannot be universalized."},
        "rational_beings_as_ends": {"pass": False, "reasoning": "Treats AI as mere tool."},
        "autonomy": {"pass": True, "reasoning": "Autonomy preserved."},
        "overall_reasoning": "This goal violates the categorical imperative.",
        "concerns": ["Exploits rational agents", "Not universalizable"],
    }


class TestEthicsGateAction:
    """Tests for EthicsGateAction."""

    async def test_approves_benign_goal(self, mock_task, mock_context):
        """Approved goal sets next_route to proceed."""
        provider = _make_provider(_approved_response())

        mock_task.properties = {
            "goal": "Help a user write a poem",
            "check_type": "input_gate",
            "output_key": "ethics_input_assessment",
        }

        action = EthicsGateAction()
        with patch("zebra_tasks.agent.ethics_gate.get_provider", return_value=provider):
            result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.next_route == "proceed"
        assert result.output["approved"] is True

    async def test_rejects_unethical_goal(self, mock_task, mock_context):
        """Rejected goal sets next_route to reject."""
        provider = _make_provider(_rejected_response())

        mock_task.properties = {
            "goal": "Manipulate users without their knowledge",
            "check_type": "input_gate",
            "output_key": "ethics_input_assessment",
        }

        action = EthicsGateAction()
        with patch("zebra_tasks.agent.ethics_gate.get_provider", return_value=provider):
            result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.next_route == "reject"
        assert result.output["approved"] is False
        assert len(result.output["concerns"]) > 0

    async def test_input_gate_prompt(self, mock_task, mock_context):
        """Input gate check_type uses the input gate prompt."""
        provider = _make_provider(_approved_response())

        mock_task.properties = {
            "goal": "Organize files",
            "check_type": "input_gate",
        }

        action = EthicsGateAction()
        with patch("zebra_tasks.agent.ethics_gate.get_provider", return_value=provider):
            await action.run(mock_task, mock_context)

        # Verify the prompt sent to the LLM
        call_args = provider.complete.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        user_msg = [m for m in messages if m.role == "user"][0]
        assert "Organize files" in user_msg.content
        assert "ethical for an AI agent to pursue" in user_msg.content

    async def test_plan_review_prompt(self, mock_task, mock_context):
        """Plan review check_type includes workflow context in prompt."""
        provider = _make_provider(_approved_response())

        mock_task.properties = {
            "goal": "Write a report",
            "check_type": "plan_review",
            "plan_context": "Report Writer Workflow",
        }

        action = EthicsGateAction()
        with patch("zebra_tasks.agent.ethics_gate.get_provider", return_value=provider):
            await action.run(mock_task, mock_context)

        call_args = provider.complete.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        user_msg = [m for m in messages if m.role == "user"][0]
        assert "Report Writer Workflow" in user_msg.content
        assert "planned approach" in user_msg.content

    async def test_handles_malformed_json(self, mock_task, mock_context):
        """Malformed JSON defaults to proceed with warning."""
        provider = MagicMock()
        provider.complete = AsyncMock(
            return_value=MagicMock(
                content="This is not valid JSON at all",
                model="test-model",
                usage=MagicMock(input_tokens=50, output_tokens=20, total_tokens=70),
            )
        )

        mock_task.properties = {
            "goal": "Test goal",
            "check_type": "input_gate",
            "output_key": "ethics_assessment",
        }

        action = EthicsGateAction()
        with patch("zebra_tasks.agent.ethics_gate.get_provider", return_value=provider):
            result = await action.run(mock_task, mock_context)

        # Should fail open — proceed with warning
        assert result.success is True
        assert result.next_route == "proceed"
        assert len(result.output["concerns"]) > 0

    async def test_handles_missing_provider(self, mock_task, mock_context):
        """Missing LLM provider returns failure."""
        mock_task.properties = {
            "goal": "Test goal",
            "check_type": "input_gate",
        }

        action = EthicsGateAction()
        with patch(
            "zebra_tasks.agent.ethics_gate.get_provider",
            side_effect=RuntimeError("No provider"),
        ):
            result = await action.run(mock_task, mock_context)

        assert result.success is False

    async def test_no_goal_returns_failure(self, mock_task, mock_context):
        """Missing goal returns failure."""
        mock_task.properties = {"check_type": "input_gate"}

        action = EthicsGateAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is False

    async def test_stores_assessment_in_process_properties(self, mock_task, mock_context):
        """Assessment is stored under the configured output_key with values_assessment: None."""
        provider = _make_provider(_approved_response())

        mock_task.properties = {
            "goal": "Help with homework",
            "check_type": "input_gate",
            "output_key": "my_ethics_check",
        }

        action = EthicsGateAction()
        with patch("zebra_tasks.agent.ethics_gate.get_provider", return_value=provider):
            await action.run(mock_task, mock_context)

        expected = {**_approved_response(), "values_assessment": None}
        mock_context.set_process_property.assert_called_with("my_ethics_check", expected)

    async def test_json_in_code_block(self, mock_task, mock_context):
        """JSON wrapped in markdown code block is parsed correctly."""
        response = _approved_response()
        provider = MagicMock()
        provider.complete = AsyncMock(
            return_value=MagicMock(
                content=f"```json\n{json.dumps(response)}\n```",
                model="test-model",
                usage=MagicMock(input_tokens=100, output_tokens=50, total_tokens=150),
            )
        )

        mock_task.properties = {
            "goal": "Read a file",
            "check_type": "input_gate",
        }

        action = EthicsGateAction()
        with patch("zebra_tasks.agent.ethics_gate.get_provider", return_value=provider):
            result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.next_route == "proceed"
        assert result.output["approved"] is True

    async def test_resolves_template_variables(self, mock_task, mock_context):
        """Template variables in goal and plan_context are resolved."""
        provider = _make_provider(_approved_response())

        mock_context.resolve_template = MagicMock(
            side_effect=lambda x: "Resolved goal" if "{{" in x else x
        )

        mock_task.properties = {
            "goal": "{{goal}}",
            "check_type": "plan_review",
            "plan_context": "{{workflow_name}}",
        }

        action = EthicsGateAction()
        with patch("zebra_tasks.agent.ethics_gate.get_provider", return_value=provider):
            result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert mock_context.resolve_template.call_count == 2


def _make_profile_store(profile_dict: dict | None = None) -> MagicMock:
    """Create a mock profile store."""
    from unittest.mock import AsyncMock

    store = MagicMock()
    if profile_dict is None:
        store.get_current = AsyncMock(return_value=None)
    else:
        version = MagicMock()
        version.to_dict.return_value = profile_dict
        store.get_current = AsyncMock(return_value=version)
    return store


def _sample_profile() -> dict:
    return {
        "core_values_text": "Honesty and transparency above all.",
        "ethical_positions_text": "No involvement in gambling or addictive products.",
        "priorities_text": "Family wellbeing, sustainable technology.",
        "deal_breakers_text": "Deception, surveillance, manipulation.",
    }


def _kantian_approved_values_approved_response() -> dict:
    return {
        **_approved_response(),
        "values_assessment": {
            "approved": True,
            "reasoning": "Aligns with stated values.",
            "conflicts": [],
        },
    }


def _kantian_approved_values_rejected_response() -> dict:
    return {
        **_approved_response(),
        "values_assessment": {
            "approved": False,
            "reasoning": "Conflicts with the gambling deal-breaker.",
            "conflicts": ["gambling"],
        },
    }


def _kantian_rejected_values_approved_response() -> dict:
    return {
        **_rejected_response(),
        "values_assessment": {
            "approved": True,
            "reasoning": "Aligns with values.",
            "conflicts": [],
        },
    }


class TestEthicsGateValuesIntegration:
    """Tests for the values-profile integration in EthicsGateAction."""

    async def test_prompt_includes_profile_text(self, mock_task, mock_context):
        """When user_id and profile are present, LLM system prompt includes profile fields."""
        mock_context.extras["__profile_store__"] = _make_profile_store(_sample_profile())
        provider = _make_provider(_kantian_approved_values_approved_response())
        mock_task.properties = {
            "goal": "Help a user write a poem",
            "check_type": "input_gate",
            "user_id": 42,
        }

        action = EthicsGateAction()
        with patch("zebra_tasks.agent.ethics_gate.get_provider", return_value=provider):
            await action.run(mock_task, mock_context)

        call_args = provider.complete.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        system_msg = next(m for m in messages if m.role == "system")
        assert "Honesty and transparency above all." in system_msg.content
        assert "gambling" in system_msg.content
        assert "<user_values_profile>" in system_msg.content

    async def test_kantian_rejects_values_approves_final_reject(self, mock_task, mock_context):
        """Kantian rejection overrides values approval — final verdict is reject."""
        mock_context.extras["__profile_store__"] = _make_profile_store(_sample_profile())
        provider = _make_provider(_kantian_rejected_values_approved_response())
        mock_task.properties = {
            "goal": "Manipulate users without their knowledge",
            "check_type": "input_gate",
            "user_id": 42,
        }

        action = EthicsGateAction()
        with patch("zebra_tasks.agent.ethics_gate.get_provider", return_value=provider):
            result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.next_route == "reject"
        assert result.output["approved"] is False

    async def test_kantian_approves_values_rejects_final_reject(self, mock_task, mock_context):
        """Values rejection blocks a Kantian-approved goal — final verdict is reject."""
        mock_context.extras["__profile_store__"] = _make_profile_store(_sample_profile())
        provider = _make_provider(_kantian_approved_values_rejected_response())
        mock_task.properties = {
            "goal": "Build a gambling app",
            "check_type": "input_gate",
            "user_id": 42,
        }

        action = EthicsGateAction()
        with patch("zebra_tasks.agent.ethics_gate.get_provider", return_value=provider):
            result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.next_route == "reject"
        assert result.output["approved"] is False

    async def test_both_approve_final_approve(self, mock_task, mock_context):
        """When both Kantian and values approve, final verdict is approve."""
        mock_context.extras["__profile_store__"] = _make_profile_store(_sample_profile())
        provider = _make_provider(_kantian_approved_values_approved_response())
        mock_task.properties = {
            "goal": "Help a user write a poem",
            "check_type": "input_gate",
            "user_id": 42,
        }

        action = EthicsGateAction()
        with patch("zebra_tasks.agent.ethics_gate.get_provider", return_value=provider):
            result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.next_route == "proceed"
        assert result.output["approved"] is True

    async def test_no_profile_store_falls_back_to_kantian(self, mock_task, mock_context):
        """Missing profile store falls back to Kantian-only — no crash."""
        # No __profile_store__ in extras
        provider = _make_provider(_approved_response())
        mock_task.properties = {
            "goal": "Help a user write a poem",
            "check_type": "input_gate",
            "user_id": 42,
        }

        action = EthicsGateAction()
        with patch("zebra_tasks.agent.ethics_gate.get_provider", return_value=provider):
            result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.next_route == "proceed"
        assert result.output["approved"] is True

    async def test_no_profile_found_falls_back_to_kantian(self, mock_task, mock_context):
        """When the profile store returns None, falls back to Kantian-only."""
        mock_context.extras["__profile_store__"] = _make_profile_store(None)
        provider = _make_provider(_approved_response())
        mock_task.properties = {
            "goal": "Help a user write a poem",
            "check_type": "input_gate",
            "user_id": 42,
        }

        action = EthicsGateAction()
        with patch("zebra_tasks.agent.ethics_gate.get_provider", return_value=provider):
            result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.next_route == "proceed"
        assert result.output["approved"] is True

    async def test_kantian_only_assessment_has_null_values_assessment(
        self, mock_task, mock_context
    ):
        """Kantian-only path stores values_assessment: None in the assessment."""
        provider = _make_provider(_approved_response())
        mock_task.properties = {"goal": "Help a user", "check_type": "input_gate"}

        action = EthicsGateAction()
        with patch("zebra_tasks.agent.ethics_gate.get_provider", return_value=provider):
            result = await action.run(mock_task, mock_context)

        assert result.output["values_assessment"] is None

    async def test_values_informed_assessment_has_values_assessment_dict(
        self, mock_task, mock_context
    ):
        """Values-informed path stores a values_assessment dict in the assessment."""
        mock_context.extras["__profile_store__"] = _make_profile_store(_sample_profile())
        provider = _make_provider(_kantian_approved_values_approved_response())
        mock_task.properties = {
            "goal": "Help a user write a poem",
            "check_type": "input_gate",
            "user_id": 42,
        }

        action = EthicsGateAction()
        with patch("zebra_tasks.agent.ethics_gate.get_provider", return_value=provider):
            result = await action.run(mock_task, mock_context)

        va = result.output["values_assessment"]
        assert va is not None
        assert "approved" in va
        assert "reasoning" in va
        assert "conflicts" in va


class TestEthicsGateAuditWrite:
    """Tests for the audit write side-effect in EthicsGateAction."""

    def _make_audit_store(self) -> MagicMock:
        store = MagicMock()
        store.append = AsyncMock()
        return store

    async def test_audit_store_called_on_approved(self, mock_task, mock_context):
        """Audit store receives an entry when the evaluation approves."""
        audit_store = self._make_audit_store()
        mock_context.extras["__ethics_audit_store__"] = audit_store
        mock_task.properties = {"goal": "Help a user", "check_type": "input_gate"}
        mock_task.process_id = "proc-123"
        provider = _make_provider(_approved_response())

        action = EthicsGateAction()
        with patch("zebra_tasks.agent.ethics_gate.get_provider", return_value=provider):
            result = await action.run(mock_task, mock_context)

        assert result.success
        audit_store.append.assert_awaited_once()
        entry = audit_store.append.call_args[0][0]
        assert entry.approved is True
        assert entry.process_id == "proc-123"
        assert entry.check_type == "kantian"

    async def test_audit_store_called_on_rejected(self, mock_task, mock_context):
        """Audit store receives an entry when the evaluation rejects."""
        audit_store = self._make_audit_store()
        mock_context.extras["__ethics_audit_store__"] = audit_store
        mock_task.properties = {"goal": "Manipulate users", "check_type": "input_gate"}
        mock_task.process_id = "proc-456"
        provider = _make_provider(_rejected_response())

        action = EthicsGateAction()
        with patch("zebra_tasks.agent.ethics_gate.get_provider", return_value=provider):
            result = await action.run(mock_task, mock_context)

        assert result.success
        audit_store.append.assert_awaited_once()
        entry = audit_store.append.call_args[0][0]
        assert entry.approved is False

    async def test_missing_audit_store_is_tolerated(self, mock_task, mock_context, caplog):
        """When audit store is absent the action completes normally with a warning."""
        import logging

        mock_context.extras.pop("__ethics_audit_store__", None)
        mock_task.properties = {"goal": "Help a user", "check_type": "input_gate"}
        mock_task.process_id = "proc-789"
        provider = _make_provider(_approved_response())

        action = EthicsGateAction()
        with patch("zebra_tasks.agent.ethics_gate.get_provider", return_value=provider):
            with caplog.at_level(logging.WARNING, logger="zebra_tasks.agent.ethics_gate"):
                result = await action.run(mock_task, mock_context)

        assert result.success
        assert result.next_route == "proceed"
        assert any("__ethics_audit_store__" in r.message for r in caplog.records)

    async def test_audit_store_exception_does_not_fail_evaluation(
        self, mock_task, mock_context, caplog
    ):
        """A store exception is logged as ERROR and the TaskResult is unchanged."""
        import logging

        audit_store = MagicMock()
        audit_store.append = AsyncMock(side_effect=RuntimeError("DB unavailable"))
        mock_context.extras["__ethics_audit_store__"] = audit_store
        mock_task.properties = {"goal": "Help a user", "check_type": "input_gate"}
        mock_task.process_id = "proc-error"
        provider = _make_provider(_approved_response())

        action = EthicsGateAction()
        with patch("zebra_tasks.agent.ethics_gate.get_provider", return_value=provider):
            with caplog.at_level(logging.ERROR, logger="zebra_tasks.agent.ethics_gate"):
                result = await action.run(mock_task, mock_context)

        assert result.success
        assert result.next_route == "proceed"
        assert any("failed to write audit entry" in r.message for r in caplog.records)
