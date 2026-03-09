"""Django ORM implementation for agent metrics tracking.

This module provides a Django-based storage backend for tracking workflow
runs and task executions, implementing the MetricsStore interface from zebra-agent.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING

from asgiref.sync import sync_to_async
from django.db.models import Avg, Count, Max, Sum
from zebra_agent.metrics import TaskExecution, WorkflowRun, WorkflowStats
from zebra_agent.storage.interfaces import MetricsStore

from .api.models import TaskExecutionModel, WorkflowRunModel

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class DjangoMetricsStore(MetricsStore):
    """Django ORM implementation for agent metrics tracking.

    Implements the MetricsStore interface using Django's ORM for
    database operations.
    """

    def __init__(self):
        """Initialize the Django metrics store."""
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the store. Django handles schema via migrations."""
        self._initialized = True
        logger.info("DjangoMetricsStore initialized")

    async def close(self) -> None:
        """Close the store. Django manages connections automatically."""
        pass

    # =========================================================================
    # Workflow Run Operations
    # =========================================================================

    async def record_run(self, run: WorkflowRun) -> None:
        """Record a workflow run."""

        @sync_to_async
        def _record():
            output_str = None
            if run.output is not None:
                if isinstance(run.output, str):
                    output_str = run.output
                else:
                    output_str = json.dumps(run.output, ensure_ascii=False, default=str)

            WorkflowRunModel.objects.update_or_create(
                id=run.id,
                defaults={
                    "workflow_name": run.workflow_name,
                    "goal": run.goal,
                    "started_at": run.started_at,
                    "completed_at": run.completed_at,
                    "success": run.success,
                    "user_rating": run.user_rating,
                    "tokens_used": run.tokens_used,
                    "error": run.error,
                    "output": output_str,
                },
            )

        await _record()

    async def update_rating(self, run_id: str, rating: int) -> None:
        """Update the user rating for a run."""
        if not 1 <= rating <= 5:
            raise ValueError("Rating must be between 1 and 5")

        @sync_to_async
        def _update():
            WorkflowRunModel.objects.filter(id=run_id).update(user_rating=rating)

        await _update()

    async def get_run(self, run_id: str) -> WorkflowRun | None:
        """Get a specific run by ID."""

        @sync_to_async
        def _get():
            try:
                model = WorkflowRunModel.objects.get(id=run_id)
                return self._model_to_run(model)
            except WorkflowRunModel.DoesNotExist:
                return None

        return await _get()

    async def get_stats(self, workflow_name: str) -> WorkflowStats:
        """Get aggregated stats for a workflow."""

        @sync_to_async
        def _get():
            queryset = WorkflowRunModel.objects.filter(workflow_name=workflow_name)
            total = queryset.count()

            if total > 0:
                successful = queryset.filter(success=True).count()
                aggs = queryset.aggregate(
                    avg_rating=Avg("user_rating"),
                    last_used=Max("started_at"),
                )
                return WorkflowStats(
                    workflow_name=workflow_name,
                    total_runs=total,
                    successful_runs=successful,
                    avg_rating=float(aggs["avg_rating"]) if aggs["avg_rating"] else None,
                    last_used=aggs["last_used"],
                )

            return WorkflowStats(workflow_name=workflow_name)

        return await _get()

    async def get_all_stats(self) -> list[WorkflowStats]:
        """Get stats for all workflows."""

        @sync_to_async
        def _get():
            results = (
                WorkflowRunModel.objects.values("workflow_name")
                .annotate(
                    total_runs=Count("id"),
                    successful_runs=Sum("success"),
                    avg_rating=Avg("user_rating"),
                    last_used=Max("started_at"),
                )
                .order_by("-total_runs")
            )

            stats = []
            for row in results:
                stats.append(
                    WorkflowStats(
                        workflow_name=row["workflow_name"],
                        total_runs=row["total_runs"],
                        successful_runs=row["successful_runs"] or 0,
                        avg_rating=float(row["avg_rating"]) if row["avg_rating"] else None,
                        last_used=row["last_used"],
                    )
                )

            return stats

        return await _get()

    async def get_recent_runs(self, limit: int = 10) -> list[WorkflowRun]:
        """Get the most recent workflow runs."""

        @sync_to_async
        def _get():
            models = WorkflowRunModel.objects.all().order_by("-started_at")[:limit]
            return [self._model_to_run(m) for m in models]

        return await _get()

    async def get_in_progress_runs(self) -> list[WorkflowRun]:
        """Get all runs that are currently in progress (not completed)."""

        @sync_to_async
        def _get():
            models = WorkflowRunModel.objects.filter(completed_at__isnull=True).order_by(
                "-started_at"
            )
            return [self._model_to_run(m) for m in models]

        return await _get()

    async def get_completed_runs(self, limit: int = 20) -> list[WorkflowRun]:
        """Get completed workflow runs, ordered by most recently completed."""

        @sync_to_async
        def _get():
            models = WorkflowRunModel.objects.filter(completed_at__isnull=False).order_by(
                "-completed_at"
            )[:limit]
            return [self._model_to_run(m) for m in models]

        return await _get()

    async def get_runs_since(self, cutoff: datetime, limit: int = 500) -> list[WorkflowRun]:
        """Get all workflow runs since the cutoff datetime, newest first."""

        @sync_to_async
        def _get():
            models = WorkflowRunModel.objects.filter(started_at__gte=cutoff).order_by(
                "-started_at"
            )[:limit]
            return [self._model_to_run(m) for m in models]

        return await _get()

    async def get_runs_for_workflow(self, workflow_name: str, limit: int = 10) -> list[WorkflowRun]:
        """Get recent runs for a specific workflow."""

        @sync_to_async
        def _get():
            models = WorkflowRunModel.objects.filter(workflow_name=workflow_name).order_by(
                "-started_at"
            )[:limit]
            return [self._model_to_run(m) for m in models]

        return await _get()

    def _model_to_run(self, model: WorkflowRunModel) -> WorkflowRun:
        """Convert Django model to WorkflowRun dataclass."""
        # Parse output if it's JSON
        output = model.output
        if output:
            try:
                output = json.loads(output)
            except (json.JSONDecodeError, TypeError):
                pass  # Keep as string

        return WorkflowRun(
            id=model.id,
            workflow_name=model.workflow_name,
            goal=model.goal,
            started_at=model.started_at,
            completed_at=model.completed_at,
            success=model.success,
            user_rating=model.user_rating,
            tokens_used=model.tokens_used or 0,
            error=model.error,
            output=output,
        )

    # =========================================================================
    # Task Execution Operations
    # =========================================================================

    async def record_task_execution(self, execution: TaskExecution) -> None:
        """Record a task execution."""

        @sync_to_async
        def _record():
            output_str = None
            if execution.output is not None:
                if isinstance(execution.output, str):
                    output_str = execution.output
                else:
                    output_str = json.dumps(execution.output, ensure_ascii=False, default=str)

            TaskExecutionModel.objects.update_or_create(
                id=execution.id,
                defaults={
                    "run_id": execution.run_id,
                    "task_definition_id": execution.task_definition_id,
                    "task_name": execution.task_name,
                    "execution_order": execution.execution_order,
                    "state": execution.state,
                    "started_at": execution.started_at,
                    "completed_at": execution.completed_at,
                    "output": output_str,
                    "error": execution.error,
                },
            )

        await _record()

    async def record_task_executions(self, executions: list[TaskExecution]) -> None:
        """Record multiple task executions in batch."""
        for execution in executions:
            await self.record_task_execution(execution)

    async def get_task_executions(self, run_id: str) -> list[TaskExecution]:
        """Get all task executions for a workflow run."""

        @sync_to_async
        def _get():
            models = TaskExecutionModel.objects.filter(run_id=run_id).order_by("execution_order")
            return [self._model_to_task_execution(m) for m in models]

        return await _get()

    def _model_to_task_execution(self, model: TaskExecutionModel) -> TaskExecution:
        """Convert Django model to TaskExecution dataclass."""
        # Parse output if it's JSON
        output = model.output
        if output:
            try:
                output = json.loads(output)
            except (json.JSONDecodeError, TypeError):
                pass  # Keep as string

        return TaskExecution(
            id=model.id,
            run_id=model.run_id,
            task_definition_id=model.task_definition_id,
            task_name=model.task_name,
            execution_order=model.execution_order,
            state=model.state,
            started_at=model.started_at,
            completed_at=model.completed_at,
            output=output,
            error=model.error,
        )
