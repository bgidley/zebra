"""In-memory implementation of the MetricsStore interface.

This module provides a pure Python in-memory storage backend for workflow metrics.
Data is lost when the process exits - suitable for testing and ephemeral use cases.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from zebra_agent.storage.interfaces import MetricsStore

if TYPE_CHECKING:
    from zebra_agent.metrics import TaskExecution, WorkflowRun, WorkflowStats

logger = logging.getLogger(__name__)


class InMemoryMetricsStore(MetricsStore):
    """In-memory implementation of workflow metrics storage.

    Stores all data in Python dicts. Data is not persisted.
    """

    def __init__(self):
        self._runs: dict[str, WorkflowRun] = {}
        self._tasks: dict[str, list[TaskExecution]] = {}  # run_id -> list of tasks
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the metrics store."""
        self._initialized = True
        logger.info("InMemoryMetricsStore initialized")

    async def close(self) -> None:
        """Close the metrics store."""
        pass

    async def _ensure_initialized(self) -> None:
        """Ensure the store is initialized."""
        if not self._initialized:
            await self.initialize()

    # =========================================================================
    # Workflow Run Operations
    # =========================================================================

    async def record_run(self, run: WorkflowRun) -> None:
        """Record a workflow run (insert or update)."""
        await self._ensure_initialized()
        self._runs[run.id] = run

    async def update_rating(self, run_id: str, rating: int) -> None:
        """Update the user rating for a run (1-5)."""
        if not 1 <= rating <= 5:
            raise ValueError("Rating must be between 1 and 5")

        await self._ensure_initialized()
        if run_id in self._runs:
            run = self._runs[run_id]
            # Import here to avoid circular import
            from zebra_agent.metrics import WorkflowRun

            # Create a new run with updated rating (dataclass is immutable pattern)
            self._runs[run_id] = WorkflowRun(
                id=run.id,
                workflow_name=run.workflow_name,
                goal=run.goal,
                started_at=run.started_at,
                completed_at=run.completed_at,
                success=run.success,
                user_rating=rating,
                tokens_used=run.tokens_used,
                error=run.error,
                output=run.output,
            )

    async def get_run(self, run_id: str) -> WorkflowRun | None:
        """Get a specific run by ID."""
        await self._ensure_initialized()
        return self._runs.get(run_id)

    async def get_stats(self, workflow_name: str) -> WorkflowStats:
        """Get aggregated stats for a workflow."""
        # Import here to avoid circular import
        from zebra_agent.metrics import WorkflowStats

        await self._ensure_initialized()

        runs = [r for r in self._runs.values() if r.workflow_name == workflow_name]

        if not runs:
            return WorkflowStats(workflow_name=workflow_name)

        total_runs = len(runs)
        successful_runs = sum(1 for r in runs if r.success)

        ratings = [r.user_rating for r in runs if r.user_rating is not None]
        avg_rating = sum(ratings) / len(ratings) if ratings else None

        last_used = max(r.started_at for r in runs)

        return WorkflowStats(
            workflow_name=workflow_name,
            total_runs=total_runs,
            successful_runs=successful_runs,
            avg_rating=avg_rating,
            last_used=last_used,
        )

    async def get_all_stats(self) -> list[WorkflowStats]:
        """Get stats for all workflows, ordered by total runs descending."""
        await self._ensure_initialized()

        # Get unique workflow names
        workflow_names = set(r.workflow_name for r in self._runs.values())

        # Get stats for each
        stats = []
        for name in workflow_names:
            stats.append(await self.get_stats(name))

        # Sort by total_runs descending
        stats.sort(key=lambda s: s.total_runs, reverse=True)
        return stats

    async def get_recent_runs(self, limit: int = 10) -> list[WorkflowRun]:
        """Get the most recent workflow runs."""
        await self._ensure_initialized()

        runs = list(self._runs.values())
        runs.sort(key=lambda r: r.started_at, reverse=True)
        return runs[:limit]

    async def get_runs_for_workflow(self, workflow_name: str, limit: int = 10) -> list[WorkflowRun]:
        """Get recent runs for a specific workflow."""
        await self._ensure_initialized()

        runs = [r for r in self._runs.values() if r.workflow_name == workflow_name]
        runs.sort(key=lambda r: r.started_at, reverse=True)
        return runs[:limit]

    # =========================================================================
    # Task Execution Operations
    # =========================================================================

    async def record_task_execution(self, execution: TaskExecution) -> None:
        """Record a task execution."""
        await self._ensure_initialized()

        if execution.run_id not in self._tasks:
            self._tasks[execution.run_id] = []

        # Check if we're updating an existing execution
        existing_idx = None
        for i, e in enumerate(self._tasks[execution.run_id]):
            if e.id == execution.id:
                existing_idx = i
                break

        if existing_idx is not None:
            self._tasks[execution.run_id][existing_idx] = execution
        else:
            self._tasks[execution.run_id].append(execution)

    async def record_task_executions(self, executions: list[TaskExecution]) -> None:
        """Record multiple task executions in batch."""
        for execution in executions:
            await self.record_task_execution(execution)

    async def get_task_executions(self, run_id: str) -> list[TaskExecution]:
        """Get all task executions for a workflow run, ordered by execution_order."""
        await self._ensure_initialized()

        tasks = self._tasks.get(run_id, [])
        return sorted(tasks, key=lambda t: t.execution_order)
