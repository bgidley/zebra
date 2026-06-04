"""Tests for user data deletion (REQ-DATA-005 / F10).

Tests:
- Soft delete marks knowledge entries as soft_deleted (deleted_at set)
- Hard delete removes all user-scoped records from all tables
- Another user's data is untouched by both modes
- DeletionReport totals are accurate
- API endpoint: soft and hard delete, confirmation requirement, auth check
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from rest_framework.test import APIClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_process(user_id, state="complete"):
    """Create a ProcessInstanceModel row for testing."""
    from django.utils import timezone
    from zebra_agent_web.api.models import ProcessInstanceModel

    return ProcessInstanceModel.objects.create(
        id=str(uuid.uuid4()),
        definition_id=str(uuid.uuid4()),
        state=state,
        user_id=user_id,
        properties="{}",
        created_at=timezone.now(),
        updated_at=timezone.now(),
    )


def _make_task(process_id, user_id):
    """Create a TaskInstanceModel row linked to a process."""
    from django.utils import timezone
    from zebra_agent_web.api.models import TaskInstanceModel

    return TaskInstanceModel.objects.create(
        id=str(uuid.uuid4()),
        process_id=process_id,
        task_definition_id="test_task",
        user_id=user_id,
        state="complete",
        foe_id=str(uuid.uuid4()),
        created_at=timezone.now(),
        updated_at=timezone.now(),
    )


def _make_foe(process_id):
    """Create a FlowOfExecutionModel row linked to a process."""
    from django.utils import timezone
    from zebra_agent_web.api.models import FlowOfExecutionModel

    return FlowOfExecutionModel.objects.create(
        id=str(uuid.uuid4()),
        process_id=process_id,
        created_at=timezone.now(),
    )


def _make_run(user_id):
    """Create a WorkflowRunModel row for a user."""
    from django.utils import timezone
    from zebra_agent_web.api.models import WorkflowRunModel

    return WorkflowRunModel.objects.create(
        id=str(uuid.uuid4()),
        workflow_name="test_workflow",
        user_id=user_id,
        goal="test goal",
        started_at=timezone.now(),
        success=True,
    )


def _make_workflow_memory(user_id):
    """Create a WorkflowMemoryModel row for a user."""
    from django.utils import timezone
    from zebra_agent_web.api.models import WorkflowMemoryModel

    return WorkflowMemoryModel.objects.create(
        id=str(uuid.uuid4()),
        user_id=user_id,
        timestamp=timezone.now(),
        workflow_name="test_workflow",
        goal="test goal",
        success=True,
        input_summary="input",
        output_summary="output",
    )


def _make_conceptual_memory(user_id):
    """Create a ConceptualMemoryModel row for a user."""
    from django.utils import timezone
    from zebra_agent_web.api.models import ConceptualMemoryModel

    return ConceptualMemoryModel.objects.create(
        id=str(uuid.uuid4()),
        user_id=user_id,
        concept="test concept",
        last_updated=timezone.now(),
    )


def _make_knowledge(user_id):
    """Create a KnowledgeEntryModel row for a user."""
    from django.utils import timezone
    from zebra_agent_web.api.models import KnowledgeEntryModel

    return KnowledgeEntryModel.objects.create(
        id=str(uuid.uuid4()),
        user_id=user_id,
        category="facts",
        key="test_key",
        value="test_value",
        last_verified=timezone.now(),
    )


# ---------------------------------------------------------------------------
# DataDeletor — hard delete
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestHardDelete:
    """Hard delete removes every user-scoped row across all tables."""

    def _run(self, user_id: int, hard: bool = True):
        from zebra_agent.deletion import DataDeletor

        async def _go():
            d = DataDeletor()
            return await d.delete_user_data(user_id, hard=hard)

        return asyncio.run(_go())

    def test_removes_processes_tasks_and_foes(self, test_user):
        uid = test_user.id
        proc = _make_process(uid)
        _make_task(proc.id, uid)
        _make_foe(proc.id)

        from zebra_agent_web.api.models import (
            FlowOfExecutionModel,
            ProcessInstanceModel,
            TaskInstanceModel,
        )

        assert ProcessInstanceModel.objects.filter(user_id=uid).count() == 1

        report = self._run(uid)

        assert ProcessInstanceModel.objects.filter(user_id=uid).count() == 0
        assert TaskInstanceModel.objects.filter(process_id=proc.id).count() == 0
        assert FlowOfExecutionModel.objects.filter(process_id=proc.id).count() == 0

        assert report.processes_deleted == 1
        assert report.tasks_deleted == 1
        assert report.foes_deleted == 1
        assert report.hard is True

    def test_removes_workflow_runs(self, test_user):
        uid = test_user.id
        _make_run(uid)

        from zebra_agent_web.api.models import WorkflowRunModel

        report = self._run(uid)

        assert WorkflowRunModel.objects.filter(user_id=uid).count() == 0
        assert report.workflow_runs_deleted == 1

    def test_removes_memories(self, test_user):
        uid = test_user.id
        _make_workflow_memory(uid)
        _make_conceptual_memory(uid)

        from zebra_agent_web.api.models import ConceptualMemoryModel, WorkflowMemoryModel

        report = self._run(uid)

        assert WorkflowMemoryModel.objects.filter(user_id=uid).count() == 0
        assert ConceptualMemoryModel.objects.filter(user_id=uid).count() == 0
        assert report.workflow_memories_deleted == 1
        assert report.conceptual_memories_deleted == 1

    def test_removes_knowledge_entries(self, test_user):
        uid = test_user.id
        _make_knowledge(uid)

        from zebra_agent_web.api.models import KnowledgeEntryModel

        report = self._run(uid)

        assert KnowledgeEntryModel.objects.filter(user_id=uid).count() == 0
        assert report.knowledge_entries_deleted == 1

    def test_leaves_other_user_data_intact(self):
        """A second user's rows must not be touched by the first user's deletion."""
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user_a = User.objects.create_user(username="user_a_del_test")
        user_b = User.objects.create_user(username="user_b_del_test")

        from zebra_agent_web.api.models import ProcessInstanceModel, WorkflowRunModel

        # Create data for both users
        proc_a = _make_process(user_a.id)
        proc_b = _make_process(user_b.id)
        run_a = _make_run(user_a.id)
        run_b = _make_run(user_b.id)

        # Hard delete user A's data
        self._run(user_a.id)

        # User A's data gone
        assert not ProcessInstanceModel.objects.filter(id=proc_a.id).exists()
        assert not WorkflowRunModel.objects.filter(id=run_a.id).exists()

        # User B's data intact
        assert ProcessInstanceModel.objects.filter(id=proc_b.id).exists()
        assert WorkflowRunModel.objects.filter(id=run_b.id).exists()

        # Cleanup
        user_a.delete()
        user_b.delete()

    def test_report_total_matches_counts(self, test_user):
        uid = test_user.id
        proc = _make_process(uid)
        _make_task(proc.id, uid)
        _make_run(uid)
        _make_knowledge(uid)

        report = self._run(uid)

        assert report.total() == (
            report.processes_deleted
            + report.tasks_deleted
            + report.foes_deleted
            + report.locks_deleted
            + report.workflow_runs_deleted
            + report.task_executions_deleted
            + report.workflow_memories_deleted
            + report.conceptual_memories_deleted
            + report.knowledge_entries_deleted
            + report.profile_versions_deleted
            + report.profiles_deleted
        )

    def test_as_dict_structure(self, test_user):
        report = self._run(test_user.id)
        d = report.as_dict()

        assert "user_id" in d
        assert "hard" in d
        assert d["hard"] is True
        assert "totals" in d
        assert "grand_total" in d["totals"]
        assert "errors" in d


# ---------------------------------------------------------------------------
# DataDeletor — soft delete
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestSoftDelete:
    """Soft delete only marks knowledge entries; other tables are untouched."""

    def _run(self, user_id: int):
        from zebra_agent.deletion import DataDeletor

        async def _go():
            d = DataDeletor()
            return await d.delete_user_data(user_id, hard=False)

        return asyncio.run(_go())

    def test_soft_deletes_knowledge_entries(self, test_user):
        uid = test_user.id
        entry = _make_knowledge(uid)

        from zebra_agent_web.api.models import KnowledgeEntryModel

        report = self._run(uid)

        # Row still exists but deleted_at is set
        row = KnowledgeEntryModel.objects.get(id=entry.id)
        assert row.deleted_at is not None
        assert report.knowledge_entries_deleted == 1

    def test_does_not_delete_processes(self, test_user):
        uid = test_user.id
        proc = _make_process(uid)

        from zebra_agent_web.api.models import ProcessInstanceModel

        self._run(uid)

        # Process row intact
        assert ProcessInstanceModel.objects.filter(id=proc.id).exists()

    def test_does_not_delete_workflow_runs(self, test_user):
        uid = test_user.id
        run = _make_run(uid)

        from zebra_agent_web.api.models import WorkflowRunModel

        self._run(uid)

        assert WorkflowRunModel.objects.filter(id=run.id).exists()

    def test_leaves_other_user_knowledge_intact(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user_a = User.objects.create_user(username="user_a_soft_test")
        user_b = User.objects.create_user(username="user_b_soft_test")

        entry_b = _make_knowledge(user_b.id)

        self._run(user_a.id)

        from zebra_agent_web.api.models import KnowledgeEntryModel

        row_b = KnowledgeEntryModel.objects.get(id=entry_b.id)
        assert row_b.deleted_at is None  # Untouched

        user_a.delete()
        user_b.delete()

    def test_idempotent_on_already_deleted_entries(self, test_user):
        uid = test_user.id
        _make_knowledge(uid)

        # First soft delete
        report1 = self._run(uid)
        assert report1.knowledge_entries_deleted == 1

        # Second soft delete — already marked, so 0 new deletions
        report2 = self._run(uid)
        assert report2.knowledge_entries_deleted == 0


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestDeleteUserDataAPI:
    """Test DELETE /api/user-data/ endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self, test_user):
        self.user = test_user
        self.client = APIClient()
        self.client.force_authenticate(user=test_user)

    def test_soft_delete_returns_200(self):
        response = self.client.delete("/api/user-data/")
        assert response.status_code == 200
        data = response.json()
        assert "totals" in data
        assert data["hard"] is False

    def test_hard_delete_requires_confirmation(self):
        response = self.client.delete("/api/user-data/?hard=true")
        assert response.status_code == 400
        assert "confirm" in response.json()["error"].lower()

    def test_hard_delete_with_confirmation_returns_200(self):
        response = self.client.delete(
            "/api/user-data/?hard=true",
            data={"confirm": "delete my data"},
            format="json",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["hard"] is True

    def test_unauthenticated_returns_403(self):
        unauth_client = APIClient()
        response = unauth_client.delete("/api/user-data/")
        assert response.status_code in (401, 403)

    def test_soft_delete_marks_knowledge_entries(self):
        uid = self.user.id
        entry = _make_knowledge(uid)

        from zebra_agent_web.api.models import KnowledgeEntryModel

        self.client.delete("/api/user-data/")

        row = KnowledgeEntryModel.objects.get(id=entry.id)
        assert row.deleted_at is not None

    def test_hard_delete_removes_processes(self):
        uid = self.user.id
        proc = _make_process(uid)

        from zebra_agent_web.api.models import ProcessInstanceModel

        self.client.delete(
            "/api/user-data/?hard=true",
            data={"confirm": "delete my data"},
            format="json",
        )

        assert not ProcessInstanceModel.objects.filter(id=proc.id).exists()

    def test_hard_delete_does_not_touch_other_users(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        other = User.objects.create_user(username="other_api_test")
        proc_other = _make_process(other.id)

        self.client.delete(
            "/api/user-data/?hard=true",
            data={"confirm": "delete my data"},
            format="json",
        )

        from zebra_agent_web.api.models import ProcessInstanceModel

        assert ProcessInstanceModel.objects.filter(id=proc_other.id).exists()
        other.delete()
