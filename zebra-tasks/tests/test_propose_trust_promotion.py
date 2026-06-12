"""Tests for ProposeTrustPromotionAction (F15 / REQ-TRUST-004)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from zebra_tasks.agent.propose_trust_promotion import ProposeTrustPromotionAction


@pytest.fixture
def mock_task():
    task = MagicMock()
    task.id = "task-1"
    task.properties = {
        "domain": "code",
        "to_level": "SEMI_AUTONOMOUS",
        "evidence": "20 clean runs",
    }
    return task


@pytest.fixture
def mock_context():
    context = MagicMock()
    context.process = MagicMock()
    context.process.properties = {"__user_id__": 1}
    context.extras = {}
    context.set_process_property = MagicMock(
        side_effect=lambda k, v: context.process.properties.__setitem__(k, v)
    )
    context.resolve_template = MagicMock(side_effect=lambda x: x)
    return context


def _suggestion_store():
    suggestion = MagicMock()
    suggestion.id = "sug-1"
    suggestion.to_level = "SEMI_AUTONOMOUS"
    suggestion.status = "pending"
    store = MagicMock(spec=["add_suggestion"])
    store.add_suggestion = AsyncMock(return_value=suggestion)
    return store


async def test_creates_pending_suggestion(mock_task, mock_context):
    store = _suggestion_store()
    mock_context.extras["__trust_store__"] = store

    result = await ProposeTrustPromotionAction().run(mock_task, mock_context)

    assert result.success
    assert result.output["submitted"] is True
    assert result.output["suggestion_id"] == "sug-1"
    assert result.output["status"] == "pending"
    store.add_suggestion.assert_awaited_once_with(1, "code", "SEMI_AUTONOMOUS", "20 clean runs")
    assert mock_context.process.properties["trust_promotion_proposal"]["submitted"] is True


async def test_action_has_no_level_mutation_path(mock_task, mock_context):
    """The store mock only exposes add_suggestion — any other call would raise."""
    mock_context.extras["__trust_store__"] = _suggestion_store()

    result = await ProposeTrustPromotionAction().run(mock_task, mock_context)

    assert result.success  # set_trust_level/resolve_suggestion never touched


async def test_missing_store_degrades_gracefully(mock_task, mock_context, caplog):
    result = await ProposeTrustPromotionAction().run(mock_task, mock_context)

    assert result.success
    assert result.output["submitted"] is False
    assert any("suggestion skipped" in r.message for r in caplog.records)


async def test_invalid_domain_or_level_fails(mock_task, mock_context):
    store = MagicMock(spec=["add_suggestion"])
    store.add_suggestion = AsyncMock(side_effect=ValueError("Unknown domain 'time-travel'"))
    mock_context.extras["__trust_store__"] = store

    result = await ProposeTrustPromotionAction().run(mock_task, mock_context)

    assert not result.success
    assert "time-travel" in result.error


async def test_missing_required_properties_fails(mock_context):
    task = MagicMock()
    task.properties = {"domain": "code"}

    result = await ProposeTrustPromotionAction().run(task, mock_context)

    assert not result.success
    assert "evidence" in result.error


async def test_missing_user_id_fails(mock_task, mock_context):
    mock_context.process.properties.pop("__user_id__")
    mock_context.extras["__trust_store__"] = _suggestion_store()

    result = await ProposeTrustPromotionAction().run(mock_task, mock_context)

    assert not result.success
    assert "user id" in result.error


async def test_templates_resolved(mock_task, mock_context):
    store = _suggestion_store()
    mock_context.extras["__trust_store__"] = store
    templates = {"{{evidence_summary}}": "handled 30 scheduling tasks"}
    mock_context.resolve_template = MagicMock(side_effect=lambda x: templates.get(x, x))
    mock_task.properties["evidence"] = "{{evidence_summary}}"

    await ProposeTrustPromotionAction().run(mock_task, mock_context)

    store.add_suggestion.assert_awaited_once_with(
        1, "code", "SEMI_AUTONOMOUS", "handled 30 scheduling tasks"
    )
