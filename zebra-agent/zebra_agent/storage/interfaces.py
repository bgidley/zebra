"""Abstract base classes for agent storage backends.

This module defines the interfaces for memory and metrics storage that can be
implemented by different backends (in-memory, Django ORM, PostgreSQL, etc.).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zebra_agent.memory import ConceptualMemoryEntry, WorkflowMemoryEntry
    from zebra_agent.metrics import TaskExecution, WorkflowRun, WorkflowStats


class MemoryStore(ABC):
    """Abstract interface for workflow-focused agent memory storage.

    Two-tier memory system:
    - Workflow Memory: Detailed per-run records of behaviour, I/O, effectiveness
    - Conceptual Memory: Compact index mapping goal patterns to workflow names

    The agent consults conceptual memory first to get a shortlist of candidates,
    then loads full details for deep selection. After each run, workflow memory
    is written and conceptual memory is incrementally updated.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the memory store."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the memory store and release resources."""
        ...

    # =========================================================================
    # Workflow Memory (Detailed per-run records)
    # =========================================================================

    @abstractmethod
    async def add_workflow_memory(self, entry: WorkflowMemoryEntry) -> None:
        """Add a detailed workflow run record to memory."""
        ...

    @abstractmethod
    async def get_workflow_memories(
        self, workflow_name: str, limit: int = 10
    ) -> list[WorkflowMemoryEntry]:
        """Get recent memory entries for a specific workflow, newest first."""
        ...

    @abstractmethod
    async def get_recent_workflow_memories(self, limit: int = 20) -> list[WorkflowMemoryEntry]:
        """Get the most recent workflow memory entries across all workflows."""
        ...

    @abstractmethod
    async def update_user_feedback(self, run_id: str, feedback: str) -> bool:
        """Update user feedback on the workflow memory entry for a run.

        Args:
            run_id: The run ID whose memory entry should be updated.
            feedback: Free-text feedback from the user.

        Returns:
            True if a matching memory entry was found and updated, False otherwise.
        """
        ...

    # =========================================================================
    # Conceptual Memory (Compact goal-pattern index)
    # =========================================================================

    @abstractmethod
    async def get_conceptual_memories(self, limit: int = 50) -> list[ConceptualMemoryEntry]:
        """Get all conceptual memory entries, most recently updated first."""
        ...

    @abstractmethod
    async def save_conceptual_memory(self, entry: ConceptualMemoryEntry) -> None:
        """Save (insert or update) a conceptual memory entry."""
        ...

    @abstractmethod
    async def clear_conceptual_memories(self) -> None:
        """Remove all conceptual memory entries (used during full rebuild)."""
        ...

    # =========================================================================
    # Context Generation
    # =========================================================================

    @abstractmethod
    async def get_conceptual_context_for_llm(self) -> str:
        """Format conceptual memory as a context string for the LLM.

        Returns a compact summary of goal patterns and recommended workflows,
        suitable for injecting into the workflow selection prompt.
        """
        ...

    @abstractmethod
    async def get_workflow_context_for_llm(self, workflow_name: str) -> str:
        """Format recent workflow memory for a specific workflow as LLM context.

        Returns a summary of past runs: what goals were served, what worked,
        what didn't, effectiveness notes.
        """
        ...

    @abstractmethod
    async def get_stats(self) -> dict:
        """Return memory statistics."""
        ...


class MetricsStore(ABC):
    """Abstract interface for workflow metrics storage.

    Tracks workflow runs and task executions for performance analysis.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the metrics store."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the metrics store and release resources."""
        ...

    # =========================================================================
    # Workflow Run Operations
    # =========================================================================

    @abstractmethod
    async def record_run(self, run: WorkflowRun) -> None:
        """Record a workflow run (insert or update)."""
        ...

    @abstractmethod
    async def update_rating(self, run_id: str, rating: int) -> None:
        """Update the user rating for a run (1-5)."""
        ...

    @abstractmethod
    async def get_run(self, run_id: str) -> WorkflowRun | None:
        """Get a specific run by ID."""
        ...

    @abstractmethod
    async def get_stats(self, workflow_name: str) -> WorkflowStats:
        """Get aggregated stats for a workflow."""
        ...

    @abstractmethod
    async def get_all_stats(self) -> list[WorkflowStats]:
        """Get stats for all workflows, ordered by total runs descending."""
        ...

    @abstractmethod
    async def get_recent_runs(self, limit: int = 10) -> list[WorkflowRun]:
        """Get the most recent workflow runs."""
        ...

    @abstractmethod
    async def get_runs_since(self, cutoff: datetime, limit: int = 500) -> list[WorkflowRun]:
        """Get all workflow runs since the cutoff datetime, newest first.

        Args:
            cutoff: Only include runs with started_at >= cutoff.
            limit: Maximum number of runs to return.

        Returns:
            List of WorkflowRun objects, ordered by started_at descending.
        """
        ...

    @abstractmethod
    async def get_runs_for_workflow(self, workflow_name: str, limit: int = 10) -> list[WorkflowRun]:
        """Get recent runs for a specific workflow."""
        ...

    @abstractmethod
    async def get_total_cost_since(self, since: datetime) -> float:
        """Return the total USD cost of all runs completed since *since*.

        Used by BudgetManager to calculate daily spend.
        """
        ...

    # =========================================================================
    # Task Execution Operations
    # =========================================================================

    @abstractmethod
    async def record_task_execution(self, execution: TaskExecution) -> None:
        """Record a task execution."""
        ...

    @abstractmethod
    async def record_task_executions(self, executions: list[TaskExecution]) -> None:
        """Record multiple task executions in batch."""
        ...

    @abstractmethod
    async def get_task_executions(self, run_id: str) -> list[TaskExecution]:
        """Get all task executions for a workflow run, ordered by execution_order."""
        ...
