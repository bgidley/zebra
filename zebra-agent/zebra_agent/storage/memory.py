"""In-memory implementation of the MemoryStore interface.

This module provides a pure Python in-memory storage backend for agent memory.
Data is lost when the process exits - suitable for testing and ephemeral use cases.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from zebra_agent.storage.interfaces import MemoryStore

if TYPE_CHECKING:
    from zebra_agent.memory import ConceptualMemoryEntry, WorkflowMemoryEntry

logger = logging.getLogger(__name__)


class InMemoryMemoryStore(MemoryStore):
    """In-memory implementation of agent memory storage.

    Stores workflow memory entries and conceptual memory entries in Python lists.
    Data is not persisted — suitable for testing and ephemeral CLI usage.
    """

    def __init__(self) -> None:
        self._workflow_memories: list[WorkflowMemoryEntry] = []
        self._conceptual_memories: list[ConceptualMemoryEntry] = []
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the memory store."""
        self._initialized = True
        logger.info("InMemoryMemoryStore initialized")

    async def close(self) -> None:
        """Close the memory store."""

    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            await self.initialize()

    # =========================================================================
    # Workflow Memory
    # =========================================================================

    async def add_workflow_memory(self, entry: WorkflowMemoryEntry) -> None:
        """Add a detailed workflow run record."""
        await self._ensure_initialized()
        self._workflow_memories.append(entry)
        self._workflow_memories.sort(key=lambda e: e.timestamp, reverse=True)

    async def get_workflow_memories(
        self, workflow_name: str, limit: int = 10
    ) -> list[WorkflowMemoryEntry]:
        """Get recent memory entries for a specific workflow, newest first."""
        await self._ensure_initialized()
        filtered = [e for e in self._workflow_memories if e.workflow_name == workflow_name]
        return filtered[:limit]

    async def get_recent_workflow_memories(self, limit: int = 20) -> list[WorkflowMemoryEntry]:
        """Get the most recent workflow memory entries across all workflows."""
        await self._ensure_initialized()
        return self._workflow_memories[:limit]

    async def update_user_feedback(self, run_id: str, feedback: str) -> bool:
        """Update user feedback on the workflow memory entry for a run."""
        await self._ensure_initialized()
        for entry in self._workflow_memories:
            if entry.run_id == run_id:
                entry.user_feedback = feedback
                return True
        return False

    # =========================================================================
    # Conceptual Memory
    # =========================================================================

    async def get_conceptual_memories(self, limit: int = 50) -> list[ConceptualMemoryEntry]:
        """Get all conceptual memory entries, most recently updated first."""
        await self._ensure_initialized()
        sorted_entries = sorted(
            self._conceptual_memories, key=lambda e: e.last_updated, reverse=True
        )
        return sorted_entries[:limit]

    async def save_conceptual_memory(self, entry: ConceptualMemoryEntry) -> None:
        """Save (insert or update) a conceptual memory entry."""
        await self._ensure_initialized()
        # Update in-place if exists, otherwise append
        for i, existing in enumerate(self._conceptual_memories):
            if existing.id == entry.id:
                self._conceptual_memories[i] = entry
                return
        self._conceptual_memories.append(entry)

    async def clear_conceptual_memories(self) -> None:
        """Remove all conceptual memory entries."""
        await self._ensure_initialized()
        self._conceptual_memories.clear()

    # =========================================================================
    # Context Generation
    # =========================================================================

    async def get_conceptual_context_for_llm(self) -> str:
        """Format conceptual memory as a context string for the LLM."""
        await self._ensure_initialized()
        entries = await self.get_conceptual_memories()
        if not entries:
            return ""

        lines = ["## Conceptual Memory (Goal Patterns → Recommended Workflows)"]
        for entry in entries:
            lines.append(f"\n### {entry.concept}")
            if entry.recommended_workflows:
                lines.append("Recommended workflows:")
                for wf in entry.recommended_workflows:
                    name = wf.get("name", "?")
                    notes = wf.get("fit_notes", "")
                    rating = wf.get("avg_rating")
                    rating_str = f" (avg rating: {rating:.1f}/5)" if rating else ""
                    lines.append(f"  - {name}{rating_str}: {notes}")
            if entry.anti_patterns:
                lines.append(f"Anti-patterns: {entry.anti_patterns}")
        return "\n".join(lines)

    async def get_workflow_context_for_llm(self, workflow_name: str) -> str:
        """Format recent workflow memory for a specific workflow as LLM context."""
        await self._ensure_initialized()
        entries = await self.get_workflow_memories(workflow_name, limit=5)
        if not entries:
            return ""

        lines = [f"## Past runs of '{workflow_name}'"]
        for entry in entries:
            status = "SUCCESS" if entry.success else "FAILED"
            rating_str = f" | rating: {entry.rating}/5" if entry.rating else ""
            model_str = f" | model: {entry.model}" if entry.model else ""
            lines.append(
                f"\n[{entry.timestamp.strftime('%Y-%m-%d')}] {status}{rating_str}{model_str}"
            )
            lines.append(f"Goal: {entry.goal}")
            lines.append(f"Output: {entry.output_summary[:200]}")
            if entry.effectiveness_notes:
                lines.append(f"Notes: {entry.effectiveness_notes[:200]}")
            if entry.user_feedback:
                lines.append(f"User feedback: {entry.user_feedback[:300]}")
        return "\n".join(lines)

    async def get_stats(self) -> dict:
        """Return memory statistics."""
        await self._ensure_initialized()
        return {
            "workflow_memory_entries": len(self._workflow_memories),
            "conceptual_memory_entries": len(self._conceptual_memories),
        }
