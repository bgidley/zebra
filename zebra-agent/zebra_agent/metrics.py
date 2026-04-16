"""Metrics dataclasses and in-memory storage for workflow performance tracking.

This module provides:
- Data classes for workflow runs, task executions, and stats
- In-memory storage implementation (via re-export)

For custom storage backends, implement the MetricsStore interface from
zebra_agent.storage.interfaces.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


@dataclass
class WorkflowRun:
    """Record of a single workflow execution."""

    id: str
    workflow_name: str
    goal: str
    started_at: datetime
    completed_at: datetime | None = None
    success: bool = False
    user_rating: int | None = None  # 1-5
    tokens_used: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0  # USD cost of this run
    error: str | None = None
    output: Any = None
    model: str | None = None  # LLM model used (e.g. "claude-sonnet-4-20250514")

    @classmethod
    def create(cls, workflow_name: str, goal: str) -> "WorkflowRun":
        """Create a new workflow run with auto-generated ID and timestamp.

        Args:
            workflow_name: Name of the workflow being executed
            goal: The user's goal or request

        Returns:
            A new WorkflowRun instance
        """
        return cls(
            id=str(uuid.uuid4()),
            workflow_name=workflow_name,
            goal=goal,
            started_at=datetime.now(UTC),
        )


@dataclass
class TaskExecution:
    """Record of a single task execution within a workflow run."""

    id: str
    run_id: str  # Foreign key to WorkflowRun.id
    task_definition_id: str  # Task ID from definition (e.g., "analyze")
    task_name: str  # Human-readable name
    execution_order: int  # Order in execution sequence (1-based)
    state: str  # "running" | "complete" | "failed" | "skipped"
    started_at: datetime
    completed_at: datetime | None = None
    output: Any = None  # Task result/output
    error: str | None = None  # Error message if failed

    @classmethod
    def create(
        cls,
        run_id: str,
        task_definition_id: str,
        task_name: str,
        execution_order: int,
    ) -> "TaskExecution":
        """Create a new task execution record with auto-generated ID and timestamp.

        Args:
            run_id: ID of the parent workflow run
            task_definition_id: Task ID from the workflow definition
            task_name: Human-readable task name
            execution_order: Order in the execution sequence (1-based)

        Returns:
            A new TaskExecution instance in "running" state
        """
        return cls(
            id=str(uuid.uuid4()),
            run_id=run_id,
            task_definition_id=task_definition_id,
            task_name=task_name,
            execution_order=execution_order,
            state="running",
            started_at=datetime.now(UTC),
        )


@dataclass
class WorkflowStats:
    """Aggregated statistics for a workflow."""

    workflow_name: str
    total_runs: int = 0
    successful_runs: int = 0
    avg_rating: float | None = None
    last_used: datetime | None = None

    @property
    def success_rate(self) -> float:
        """Calculate success rate as a fraction (0.0 to 1.0)."""
        if self.total_runs == 0:
            return 0.0
        return self.successful_runs / self.total_runs


def __getattr__(name: str):
    """Lazy import for MetricsStore to avoid circular import."""
    if name == "MetricsStore":
        from zebra_agent.storage.metrics import InMemoryMetricsStore

        return InMemoryMetricsStore
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "WorkflowRun",
    "TaskExecution",
    "WorkflowStats",
    "MetricsStore",  # noqa: F822 - resolved via __getattr__ (backward-compat alias for InMemoryMetricsStore)
]
