"""Tests for TrustGateAction - per-domain trust level enforcement (F13 / REQ-TRUST-003)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zebra_tasks.agent.reversibility import ReversibilityAssessment
from zebra_tasks.agent.trust_gate import ASSESSMENTS_KEY, DECISIONS_KEY, TrustGateAction


def _assessment(reversible: bool) -> ReversibilityAssessment:
    return ReversibilityAssessment(
        reversible=reversible,
        reasoning="judged",
        confidence=0.9,
        chain_notes="none",
        source="llm",
    )


@pytest.fixture
def mock_task():
    """Create a mock task instance."""
    task = MagicMock()
    task.id = "task-1"
    task.process_id = "process-1"
    task.properties = {"domain": "code"}
    return task


@pytest.fixture
def mock_context():
    """Create a mock execution context."""
    context = MagicMock()
    context.process = MagicMock()
    context.process.id = "process-1"
    context.process.properties = {"__user_id__": 1}
    context.extras = {}
    context.set_process_property = MagicMock(
        side_effect=lambda k, v: context.process.properties.__setitem__(k, v)
    )
    context.resolve_template = MagicMock(side_effect=lambda x: x)
    return context


def _store_with_level(level: str) -> MagicMock:
    store = MagicMock()
    store.get_trust_level = AsyncMock(return_value=level)
    return store


class TestRouting:
    async def test_supervised_routes_to_approve(self, mock_task, mock_context):
        mock_context.extras["__trust_store__"] = _store_with_level("SUPERVISED")

        result = await TrustGateAction().run(mock_task, mock_context)

        assert result.success
        assert result.next_route == "approve"
        assert result.output["level"] == "SUPERVISED"

    async def test_autonomous_proceeds(self, mock_task, mock_context):
        mock_context.extras["__trust_store__"] = _store_with_level("AUTONOMOUS")

        result = await TrustGateAction().run(mock_task, mock_context)

        assert result.next_route == "proceed"
        assert result.output["level"] == "AUTONOMOUS"

    async def test_semi_autonomous_reversible_assessment_proceeds(self, mock_task, mock_context):
        mock_context.extras["__trust_store__"] = _store_with_level("SEMI_AUTONOMOUS")
        mock_task.properties["action_description"] = "draft a reply"

        with patch(
            "zebra_tasks.agent.trust_gate.assess_reversibility",
            new=AsyncMock(return_value=_assessment(True)),
        ):
            result = await TrustGateAction().run(mock_task, mock_context)

        assert result.next_route == "proceed"
        assert "assessed reversible" in result.output["reason"]

    async def test_semi_autonomous_irreversible_assessment_requires_approval(
        self, mock_task, mock_context
    ):
        mock_context.extras["__trust_store__"] = _store_with_level("SEMI_AUTONOMOUS")
        mock_task.properties["action_description"] = "delete prod config"

        with patch(
            "zebra_tasks.agent.trust_gate.assess_reversibility",
            new=AsyncMock(return_value=_assessment(False)),
        ):
            result = await TrustGateAction().run(mock_task, mock_context)

        assert result.next_route == "approve"
        assert "assessed irreversible" in result.output["reason"]

    async def test_semi_autonomous_declaration_does_not_bypass_assessment(
        self, mock_task, mock_context
    ):
        """A static reversibility declaration is context only — assessment wins."""
        mock_context.extras["__trust_store__"] = _store_with_level("SEMI_AUTONOMOUS")
        mock_task.properties["reversibility"] = "reversible"
        mock_task.properties["action_description"] = "delete prod config"

        with patch(
            "zebra_tasks.agent.trust_gate.assess_reversibility",
            new=AsyncMock(return_value=_assessment(False)),
        ) as assess:
            result = await TrustGateAction().run(mock_task, mock_context)

        assert result.next_route == "approve"
        assert assess.call_args.kwargs["declared"] == "reversible"

    async def test_semi_autonomous_nothing_to_assess_fails_closed(self, mock_task, mock_context):
        """No target_task_id and no action_description -> approve without LLM."""
        mock_context.extras["__trust_store__"] = _store_with_level("SEMI_AUTONOMOUS")

        with patch("zebra_tasks.agent.reversibility.get_provider") as get_provider:
            result = await TrustGateAction().run(mock_task, mock_context)

        get_provider.assert_not_called()
        assert result.next_route == "approve"
        assert result.output["assessment"]["source"] == "fail_closed"

    async def test_supervised_and_autonomous_never_assess(self, mock_task, mock_context):
        mock_task.properties["action_description"] = "anything"
        with patch("zebra_tasks.agent.trust_gate.assess_reversibility", new=AsyncMock()) as assess:
            mock_context.extras["__trust_store__"] = _store_with_level("SUPERVISED")
            await TrustGateAction().run(mock_task, mock_context)
            mock_context.extras["__trust_store__"] = _store_with_level("AUTONOMOUS")
            await TrustGateAction().run(mock_task, mock_context)

        assess.assert_not_awaited()

    async def test_assessment_recorded_in_audit_trail(self, mock_task, mock_context):
        mock_context.extras["__trust_store__"] = _store_with_level("SEMI_AUTONOMOUS")
        mock_task.properties["action_description"] = "draft a reply"

        with patch(
            "zebra_tasks.agent.trust_gate.assess_reversibility",
            new=AsyncMock(return_value=_assessment(True)),
        ):
            result = await TrustGateAction().run(mock_task, mock_context)

        assessments = mock_context.process.properties[ASSESSMENTS_KEY]
        assert len(assessments) == 1
        assert assessments[0]["reversible"] is True
        assert result.output["assessment"] == assessments[0]

    async def test_store_queried_with_resolved_user_and_domain(self, mock_task, mock_context):
        store = _store_with_level("AUTONOMOUS")
        mock_context.extras["__trust_store__"] = store
        mock_task.properties = {"domain": "finance", "user_id": 7}

        await TrustGateAction().run(mock_task, mock_context)

        store.get_trust_level.assert_awaited_once_with(7, "finance")


class TestFailClosed:
    async def test_missing_store_routes_to_approve(self, mock_task, mock_context, caplog):
        result = await TrustGateAction().run(mock_task, mock_context)

        assert result.success
        assert result.next_route == "approve"
        assert "failing closed" in result.output["reason"]
        assert any(
            "trust_store" in r.message or "failing closed" in r.message for r in caplog.records
        )

    async def test_missing_user_id_routes_to_approve(self, mock_task, mock_context):
        mock_context.extras["__trust_store__"] = _store_with_level("AUTONOMOUS")
        mock_context.process.properties.pop("__user_id__")

        result = await TrustGateAction().run(mock_task, mock_context)

        assert result.next_route == "approve"
        assert "no resolvable user id" in result.output["reason"]

    async def test_store_error_routes_to_approve(self, mock_task, mock_context):
        store = MagicMock()
        store.get_trust_level = AsyncMock(side_effect=RuntimeError("oracle down"))
        mock_context.extras["__trust_store__"] = store

        result = await TrustGateAction().run(mock_task, mock_context)

        assert result.next_route == "approve"
        assert "trust store error" in result.output["reason"]

    async def test_unrecognised_level_routes_to_approve(self, mock_task, mock_context):
        mock_context.extras["__trust_store__"] = _store_with_level("OMNIPOTENT")

        result = await TrustGateAction().run(mock_task, mock_context)

        assert result.next_route == "approve"
        assert "unrecognised trust level" in result.output["reason"]

    async def test_missing_domain_fails(self, mock_task, mock_context):
        mock_task.properties = {}

        result = await TrustGateAction().run(mock_task, mock_context)

        assert not result.success
        assert "domain" in result.error


class TestAudit:
    async def test_decision_recorded_in_process_properties(self, mock_task, mock_context):
        mock_context.extras["__trust_store__"] = _store_with_level("SUPERVISED")
        mock_task.properties["action_description"] = "delete production database"

        result = await TrustGateAction().run(mock_task, mock_context)

        decisions = mock_context.process.properties[DECISIONS_KEY]
        assert len(decisions) == 1
        decision = decisions[0]
        assert decision == result.output
        assert decision["task_id"] == "task-1"
        assert decision["domain"] == "code"
        assert decision["user_id"] == 1
        assert decision["action_description"] == "delete production database"
        assert decision["level"] == "SUPERVISED"
        assert decision["route"] == "approve"
        assert decision["reason"]
        assert decision["decided_at"]

    async def test_decisions_accumulate_in_order(self, mock_task, mock_context):
        mock_context.extras["__trust_store__"] = _store_with_level("SUPERVISED")

        await TrustGateAction().run(mock_task, mock_context)
        second_task = MagicMock()
        second_task.id = "task-2"
        second_task.properties = {"domain": "home"}
        await TrustGateAction().run(second_task, mock_context)

        decisions = mock_context.process.properties[DECISIONS_KEY]
        assert [d["task_id"] for d in decisions] == ["task-1", "task-2"]
        assert [d["domain"] for d in decisions] == ["code", "home"]

    async def test_decision_stored_under_output_key(self, mock_task, mock_context):
        mock_context.extras["__trust_store__"] = _store_with_level("AUTONOMOUS")
        mock_task.properties["output_key"] = "gate_result"

        await TrustGateAction().run(mock_task, mock_context)

        assert mock_context.process.properties["gate_result"]["route"] == "proceed"


class TestTemplates:
    async def test_templates_resolved(self, mock_task, mock_context):
        store = _store_with_level("AUTONOMOUS")
        mock_context.extras["__trust_store__"] = store
        templates = {
            "{{the_domain}}": "scheduling",
            "{{uid}}": "9",
            "{{planned_action}}": "book a meeting",
        }
        mock_context.resolve_template = MagicMock(side_effect=lambda x: templates.get(x, x))
        mock_task.properties = {
            "domain": "{{the_domain}}",
            "user_id": "{{uid}}",
            "action_description": "{{planned_action}}",
        }

        result = await TrustGateAction().run(mock_task, mock_context)

        store.get_trust_level.assert_awaited_once_with(9, "scheduling")
        assert result.output["domain"] == "scheduling"
        assert result.output["action_description"] == "book a meeting"
