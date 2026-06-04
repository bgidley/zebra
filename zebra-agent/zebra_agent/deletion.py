"""Data deletion service for user-scoped data (REQ-DATA-005 / F10).

Two modes:
- Soft delete: marks records as soft_deleted; retained for audit.
- Hard delete: removes every row scoped to that user (irreversible).

The service works through ORM models imported lazily so that it can be used
from both the Django web app and future CLI contexts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class DeletionReport:
    """Summary of records deleted or marked deleted."""

    user_id: int
    hard: bool
    processes_deleted: int = 0
    tasks_deleted: int = 0
    foes_deleted: int = 0
    locks_deleted: int = 0
    workflow_runs_deleted: int = 0
    task_executions_deleted: int = 0
    workflow_memories_deleted: int = 0
    conceptual_memories_deleted: int = 0
    knowledge_entries_deleted: int = 0
    profile_versions_deleted: int = 0
    profiles_deleted: int = 0
    errors: list[str] = field(default_factory=list)

    def total(self) -> int:
        """Return total count of deleted / soft-deleted records."""
        return (
            self.processes_deleted
            + self.tasks_deleted
            + self.foes_deleted
            + self.locks_deleted
            + self.workflow_runs_deleted
            + self.task_executions_deleted
            + self.workflow_memories_deleted
            + self.conceptual_memories_deleted
            + self.knowledge_entries_deleted
            + self.profile_versions_deleted
            + self.profiles_deleted
        )

    def as_dict(self) -> dict:
        """Return a plain dict suitable for JSON serialisation."""
        return {
            "user_id": self.user_id,
            "hard": self.hard,
            "totals": {
                "processes": self.processes_deleted,
                "tasks": self.tasks_deleted,
                "flows_of_execution": self.foes_deleted,
                "process_locks": self.locks_deleted,
                "workflow_runs": self.workflow_runs_deleted,
                "task_executions": self.task_executions_deleted,
                "workflow_memories": self.workflow_memories_deleted,
                "conceptual_memories": self.conceptual_memories_deleted,
                "knowledge_entries": self.knowledge_entries_deleted,
                "profile_versions": self.profile_versions_deleted,
                "profiles": self.profiles_deleted,
                "grand_total": self.total(),
            },
            "errors": self.errors,
        }


class DataDeletor:
    """Deletes or soft-deletes all data scoped to a user.

    This service imports Django ORM models lazily so that it can be imported
    from non-Django contexts without side effects.

    Hard delete removes every row with ``user_id = user_id`` from:
    - ProcessInstanceModel (and TaskInstanceModel, FlowOfExecutionModel, ProcessLockModel)
    - WorkflowRunModel (and TaskExecutionModel via CASCADE)
    - WorkflowMemoryModel
    - ConceptualMemoryModel
    - KnowledgeEntryModel
    - ValuesProfileVersionModel / ValuesProfileModel

    Ethics audit entries are intentionally excluded from hard delete — they are
    an append-only audit trail. Routine run rows have no user scoping.
    """

    async def delete_user_data(self, user_id: int, hard: bool = False) -> DeletionReport:
        """Delete all data for user_id.

        Args:
            user_id: The Django auth user id whose data will be removed.
            hard: If True, rows are physically deleted. If False (soft delete),
                  only KnowledgeEntryModel rows are soft-deleted (deleted_at set);
                  other records have no soft-delete column and are left intact.

        Returns:
            DeletionReport with counts of affected records.
        """
        from asgiref.sync import sync_to_async

        report = DeletionReport(user_id=user_id, hard=hard)

        if hard:

            @sync_to_async(thread_sensitive=False)
            def _hard_delete():
                return self._hard_delete_sync(user_id, report)

            await _hard_delete()
        else:

            @sync_to_async(thread_sensitive=False)
            def _soft_delete():
                return self._soft_delete_sync(user_id, report)

            await _soft_delete()

        logger.info(
            "Data deletion complete: user=%s hard=%s total=%d",
            user_id,
            hard,
            report.total(),
        )
        return report

    # ------------------------------------------------------------------
    # Private implementation helpers (all run inside sync_to_async)
    # ------------------------------------------------------------------

    def _hard_delete_sync(self, user_id: int, report: DeletionReport) -> None:
        """Physically delete every user-scoped row."""
        from django.db import transaction
        from zebra_agent_web.api.models import (
            ConceptualMemoryModel,
            FlowOfExecutionModel,
            KnowledgeEntryModel,
            ProcessInstanceModel,
            ProcessLockModel,
            TaskInstanceModel,
            ValuesProfileModel,
            ValuesProfileVersionModel,
            WorkflowMemoryModel,
            WorkflowRunModel,
        )

        with transaction.atomic():
            # --- Process engine data ---
            # Collect process IDs for this user first
            process_ids = list(
                ProcessInstanceModel.objects.filter(user_id=user_id).values_list("id", flat=True)
            )

            if process_ids:
                n, _ = TaskInstanceModel.objects.filter(process_id__in=process_ids).delete()
                report.tasks_deleted += n

                n, _ = FlowOfExecutionModel.objects.filter(process_id__in=process_ids).delete()
                report.foes_deleted += n

                n, _ = ProcessLockModel.objects.filter(process_id__in=process_ids).delete()
                report.locks_deleted += n

            n, _ = ProcessInstanceModel.objects.filter(user_id=user_id).delete()
            report.processes_deleted += n

            # --- Metrics ---
            # TaskExecutionModel cascades from WorkflowRunModel
            n, _ = WorkflowRunModel.objects.filter(user_id=user_id).delete()
            report.workflow_runs_deleted += n

            # --- Memory ---
            n, _ = WorkflowMemoryModel.objects.filter(user_id=user_id).delete()
            report.workflow_memories_deleted += n

            n, _ = ConceptualMemoryModel.objects.filter(user_id=user_id).delete()
            report.conceptual_memories_deleted += n

            # --- Knowledge ---
            n, _ = KnowledgeEntryModel.objects.filter(user_id=user_id).delete()
            report.knowledge_entries_deleted += n

            # --- Values profile ---
            # ValuesProfileVersionModel cascades from ValuesProfileModel
            profile_ids = list(
                ValuesProfileModel.objects.filter(user_id=user_id).values_list("id", flat=True)
            )
            if profile_ids:
                n, _ = ValuesProfileVersionModel.objects.filter(profile_id__in=profile_ids).delete()
                report.profile_versions_deleted += n

            n, _ = ValuesProfileModel.objects.filter(user_id=user_id).delete()
            report.profiles_deleted += n

    def _soft_delete_sync(self, user_id: int, report: DeletionReport) -> None:
        """Soft-delete user data where supported (knowledge entries only).

        Other models (processes, memories, metrics) have no soft-delete column.
        Only KnowledgeEntryModel supports soft-delete via ``deleted_at``.
        """
        from django.utils import timezone
        from zebra_agent_web.api.models import KnowledgeEntryModel

        now = timezone.now()
        n = KnowledgeEntryModel.objects.filter(user_id=user_id, deleted_at__isnull=True).update(
            deleted_at=now
        )
        report.knowledge_entries_deleted += n
