"""Abstract base classes for agent storage backends.

This module defines the interfaces for memory and metrics storage that can be
implemented by different backends (in-memory, Django ORM, PostgreSQL, etc.).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zebra_agent.memory import LongTermTheme, MemoryEntry, ShortTermSummary
    from zebra_agent.metrics import TaskExecution, WorkflowRun, WorkflowStats


class MemoryStore(ABC):
    """Abstract interface for agent memory storage.

    Memory is organized in two tiers:
    - Short-term: Recent interaction entries that get compacted into summaries
    - Long-term: Thematic summaries extracted from short-term summaries
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
    # Short-Term Memory Operations
    # =========================================================================

    @abstractmethod
    async def add_entry(self, entry: "MemoryEntry") -> None:
        """Add a memory entry to short-term storage."""
        ...

    @abstractmethod
    async def get_short_term_entries(self, limit: int | None = None) -> list["MemoryEntry"]:
        """Get recent entries, ordered by timestamp descending (newest first)."""
        ...

    @abstractmethod
    async def get_short_term_tokens(self) -> int:
        """Get total token count of all short-term entries."""
        ...

    @abstractmethod
    async def get_short_term_summary_tokens(self) -> int:
        """Get total token count of all short-term summaries."""
        ...

    @abstractmethod
    async def needs_short_term_compaction(self) -> bool:
        """Check if short-term memory needs compaction (above threshold)."""
        ...

    @abstractmethod
    async def get_short_term_summaries(self, limit: int | None = None) -> list["ShortTermSummary"]:
        """Get short-term summaries, ordered by creation time descending."""
        ...

    @abstractmethod
    async def get_short_term_summary_by_id(self, summary_id: str) -> "ShortTermSummary | None":
        """Get a specific short-term summary by ID."""
        ...

    @abstractmethod
    async def add_short_term_summary(self, summary: "ShortTermSummary") -> None:
        """Add a compacted summary to short-term storage."""
        ...

    @abstractmethod
    async def clear_short_term_entries(self) -> None:
        """Clear all short-term entries (after compaction)."""
        ...

    @abstractmethod
    async def get_short_term_content_for_compaction(self) -> str:
        """Format entries as text for LLM compaction."""
        ...

    # =========================================================================
    # Long-Term Memory Operations
    # =========================================================================

    @abstractmethod
    async def get_long_term_tokens(self) -> int:
        """Get total token count of all long-term themes."""
        ...

    @abstractmethod
    async def needs_long_term_compaction(self) -> bool:
        """Check if long-term memory needs compaction (above threshold)."""
        ...

    @abstractmethod
    async def get_long_term_themes(self, limit: int | None = None) -> list["LongTermTheme"]:
        """Get long-term themes, ordered by creation time descending."""
        ...

    @abstractmethod
    async def add_long_term_theme(self, theme: "LongTermTheme") -> None:
        """Add a theme to long-term storage."""
        ...

    @abstractmethod
    async def clear_short_term_summaries(self, keep_ids: list[str] | None = None) -> None:
        """Clear short-term summaries, optionally keeping specified IDs."""
        ...

    @abstractmethod
    async def get_long_term_content_for_compaction(self) -> str:
        """Format themes and summaries as text for LLM compaction."""
        ...

    @abstractmethod
    async def get_details_for_theme(self, theme: "LongTermTheme") -> str:
        """Get detailed summary content referenced by a theme."""
        ...

    # =========================================================================
    # Context Generation
    # =========================================================================

    @abstractmethod
    async def get_context_for_llm(self) -> str:
        """Build context string for LLM (themes + summaries + entries)."""
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
    async def record_run(self, run: "WorkflowRun") -> None:
        """Record a workflow run (insert or update)."""
        ...

    @abstractmethod
    async def update_rating(self, run_id: str, rating: int) -> None:
        """Update the user rating for a run (1-5)."""
        ...

    @abstractmethod
    async def get_run(self, run_id: str) -> "WorkflowRun | None":
        """Get a specific run by ID."""
        ...

    @abstractmethod
    async def get_stats(self, workflow_name: str) -> "WorkflowStats":
        """Get aggregated stats for a workflow."""
        ...

    @abstractmethod
    async def get_all_stats(self) -> list["WorkflowStats"]:
        """Get stats for all workflows, ordered by total runs descending."""
        ...

    @abstractmethod
    async def get_recent_runs(self, limit: int = 10) -> list["WorkflowRun"]:
        """Get the most recent workflow runs."""
        ...

    @abstractmethod
    async def get_runs_for_workflow(
        self, workflow_name: str, limit: int = 10
    ) -> list["WorkflowRun"]:
        """Get recent runs for a specific workflow."""
        ...

    # =========================================================================
    # Task Execution Operations
    # =========================================================================

    @abstractmethod
    async def record_task_execution(self, execution: "TaskExecution") -> None:
        """Record a task execution."""
        ...

    @abstractmethod
    async def record_task_executions(self, executions: list["TaskExecution"]) -> None:
        """Record multiple task executions in batch."""
        ...

    @abstractmethod
    async def get_task_executions(self, run_id: str) -> list["TaskExecution"]:
        """Get all task executions for a workflow run, ordered by execution_order."""
        ...
