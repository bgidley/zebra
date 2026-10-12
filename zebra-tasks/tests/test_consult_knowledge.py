"""Tests for ConsultKnowledgeAction."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from zebra_agent.knowledge import KnowledgeEntry


def _entry(category: str, key: str, value: str) -> KnowledgeEntry:
    now = datetime(2026, 10, 1, tzinfo=UTC)
    return KnowledgeEntry(
        id=f"{category}-{key}",
        user_id=42,
        category=category,
        key=key,
        value=value,
        source="human",
        confidence=1.0,
        last_verified=now,
        created_at=now,
    )


@pytest.fixture
def mock_task():
    task = MagicMock()
    task.id = "task-1"
    task.properties = {"goal": "Test goal", "output_key": "knowledge_context"}
    return task


@pytest.fixture
def mock_context():
    context = MagicMock()
    context.process = MagicMock()
    context.process.id = "process-1"
    context.process.properties = {"__user_id__": 42}
    context.extras = {}
    context.get_process_property = MagicMock(
        side_effect=lambda k, d=None: context.process.properties.get(k, d)
    )
    context.set_process_property = MagicMock(
        side_effect=lambda k, v: context.process.properties.__setitem__(k, v)
    )
    context.resolve_template = MagicMock(side_effect=lambda x: x)
    return context


@pytest.fixture
def mock_knowledge_store():
    store = MagicMock()
    store.search_entries = AsyncMock(
        return_value=[
            _entry("preferences", "theme", "dark mode"),
            _entry("facts", "employer", "Acme"),
        ]
    )
    store.get_context_for_llm = AsyncMock(return_value="[preferences] theme: dark mode")
    return store


class TestConsultKnowledgeAction:
    async def test_happy_path_returns_knowledge(
        self, mock_task, mock_context, mock_knowledge_store
    ):
        from zebra_tasks.agent.consult_knowledge import ConsultKnowledgeAction

        mock_context.extras["__knowledge_store__"] = mock_knowledge_store
        action = ConsultKnowledgeAction()
        result = await action.run(mock_task, mock_context)

        assert result.success
        assert result.output["has_knowledge"] is True
        assert result.output["knowledge"] == (
            "[preferences] theme: dark mode\n[facts] employer: Acme"
        )
        # Goal-relevant entries (#169)
        mock_knowledge_store.search_entries.assert_awaited_once_with(42, "Test goal", limit=20)
        mock_knowledge_store.get_context_for_llm.assert_not_called()

    async def test_no_goal_falls_back_to_recent_entries(
        self, mock_task, mock_context, mock_knowledge_store
    ):
        from zebra_tasks.agent.consult_knowledge import ConsultKnowledgeAction

        mock_task.properties = {"output_key": "knowledge_context"}
        mock_context.extras["__knowledge_store__"] = mock_knowledge_store
        result = await ConsultKnowledgeAction().run(mock_task, mock_context)

        assert result.output["knowledge"] == "[preferences] theme: dark mode"
        mock_knowledge_store.get_context_for_llm.assert_awaited_once_with(42)
        mock_knowledge_store.search_entries.assert_not_called()

    async def test_no_store_degrades_gracefully(self, mock_task, mock_context):
        from zebra_tasks.agent.consult_knowledge import ConsultKnowledgeAction

        action = ConsultKnowledgeAction()
        result = await action.run(mock_task, mock_context)

        assert result.success
        assert result.output["knowledge"] == ""
        assert result.output["has_knowledge"] is False

    async def test_none_user_id_degrades_gracefully(
        self, mock_task, mock_context, mock_knowledge_store
    ):
        from zebra_tasks.agent.consult_knowledge import ConsultKnowledgeAction

        mock_context.extras["__knowledge_store__"] = mock_knowledge_store
        mock_context.process.properties["__user_id__"] = None
        action = ConsultKnowledgeAction()
        result = await action.run(mock_task, mock_context)

        assert result.success
        assert result.output["knowledge"] == ""
        assert result.output["has_knowledge"] is False
        mock_knowledge_store.search_entries.assert_not_called()

    async def test_empty_store_returns_has_knowledge_false(
        self, mock_task, mock_context, mock_knowledge_store
    ):
        from zebra_tasks.agent.consult_knowledge import ConsultKnowledgeAction

        mock_knowledge_store.search_entries = AsyncMock(return_value=[])
        mock_context.extras["__knowledge_store__"] = mock_knowledge_store
        action = ConsultKnowledgeAction()
        result = await action.run(mock_task, mock_context)

        assert result.success
        assert result.output["has_knowledge"] is False
        assert result.output["knowledge"] == ""

    async def test_store_exception_degrades_gracefully(
        self, mock_task, mock_context, mock_knowledge_store
    ):
        from zebra_tasks.agent.consult_knowledge import ConsultKnowledgeAction

        mock_knowledge_store.search_entries = AsyncMock(side_effect=RuntimeError("db error"))
        mock_context.extras["__knowledge_store__"] = mock_knowledge_store
        action = ConsultKnowledgeAction()
        result = await action.run(mock_task, mock_context)

        assert result.success
        assert result.output["knowledge"] == ""
        assert result.output["has_knowledge"] is False

    async def test_result_stored_in_process_property(
        self, mock_task, mock_context, mock_knowledge_store
    ):
        from zebra_tasks.agent.consult_knowledge import ConsultKnowledgeAction

        mock_context.extras["__knowledge_store__"] = mock_knowledge_store
        action = ConsultKnowledgeAction()
        await action.run(mock_task, mock_context)

        assert mock_context.process.properties["knowledge_context"]["has_knowledge"] is True
