"""In-memory implementations of storage interfaces.

Provides pure Python in-memory storage backends for agent memory and the
personal knowledge store. Data is lost when the process exits — suitable
for testing and ephemeral CLI use cases.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from zebra_agent.storage.interfaces import CompactionBatch, MemoryStore, PersonalKnowledgeStore

if TYPE_CHECKING:
    from zebra_agent.knowledge import KnowledgeEntry
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

    async def get_workflow_memory_by_run_id(self, run_id: str) -> WorkflowMemoryEntry | None:
        """Return the workflow memory entry for a specific run, or None if not found."""
        await self._ensure_initialized()
        for entry in self._workflow_memories:
            if entry.run_id == run_id:
                return entry
        return None

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

    # =========================================================================
    # Compaction (Tiered retention)
    # =========================================================================

    async def get_entries_for_compaction(self, now: datetime) -> CompactionBatch:
        """Return entries that have crossed a tier boundary since last compaction."""
        from datetime import timedelta

        from zebra_agent.memory import ConceptualMemoryEntry, WorkflowMemoryEntry

        await self._ensure_initialized()
        warm_cutoff = now - timedelta(weeks=2)
        cold_cutoff = now - timedelta(days=60)

        batch: CompactionBatch = CompactionBatch()
        for entry in self._workflow_memories:
            if entry.timestamp <= cold_cutoff and entry.tier != "cold":
                batch.cold_workflow.append(entry)
            elif entry.timestamp <= warm_cutoff and entry.tier == "hot":
                batch.warm_workflow.append(entry)

        for entry in self._conceptual_memories:
            if entry.last_updated <= cold_cutoff and entry.tier != "cold":
                batch.cold_conceptual.append(entry)
            elif entry.last_updated <= warm_cutoff and entry.tier == "hot":
                batch.warm_conceptual.append(entry)

        return batch

    async def update_workflow_memory_tier(
        self,
        entry_id: str,
        tier: str,
        output_summary: str | None = None,
        effectiveness_notes: str | None = None,
    ) -> None:
        """Update tier and optionally compressed fields on a WorkflowMemoryEntry."""
        await self._ensure_initialized()
        for entry in self._workflow_memories:
            if entry.id == entry_id:
                entry.tier = tier
                if output_summary is not None:
                    entry.output_summary = output_summary
                if effectiveness_notes is not None:
                    entry.effectiveness_notes = effectiveness_notes
                return

    async def update_conceptual_memory_tier(
        self,
        entry_id: str,
        tier: str,
        recommended_workflows: list[dict] | None = None,
        anti_patterns: str | None = None,
    ) -> None:
        """Update tier and optionally trimmed fields on a ConceptualMemoryEntry."""
        await self._ensure_initialized()
        for entry in self._conceptual_memories:
            if entry.id == entry_id:
                entry.tier = tier
                if recommended_workflows is not None:
                    entry.recommended_workflows = recommended_workflows
                if anti_patterns is not None:
                    entry.anti_patterns = anti_patterns
                return


class InMemoryPersonalKnowledgeStore(PersonalKnowledgeStore):
    """In-memory implementation of the personal knowledge store.

    Stores entries in a plain dict keyed by entry ID. Suitable for CLI
    and test use cases where persistence is not required.
    """

    def __init__(self) -> None:
        self._entries: dict[str, KnowledgeEntry] = {}
        self._initialized = False

    async def initialize(self) -> None:
        self._initialized = True
        logger.info("InMemoryPersonalKnowledgeStore initialized")

    async def close(self) -> None:
        pass

    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            await self.initialize()

    async def add_entry(self, entry: KnowledgeEntry) -> None:
        await self._ensure_initialized()
        self._entries[entry.id] = entry

    async def update_entry(self, entry: KnowledgeEntry) -> None:
        await self._ensure_initialized()
        self._entries[entry.id] = entry

    async def soft_delete_entry(self, entry_id: str) -> bool:
        await self._ensure_initialized()
        entry = self._entries.get(entry_id)
        if entry is None:
            return False
        from datetime import UTC, datetime

        entry.deleted_at = datetime.now(UTC)
        return True

    async def get_entry(self, entry_id: str) -> KnowledgeEntry | None:
        await self._ensure_initialized()
        return self._entries.get(entry_id)

    async def get_entries(
        self,
        user_id: int,
        category: str | None = None,
        include_deleted: bool = False,
    ) -> list[KnowledgeEntry]:
        await self._ensure_initialized()
        results = [e for e in self._entries.values() if e.user_id == user_id]
        if not include_deleted:
            results = [e for e in results if e.deleted_at is None]
        if category is not None:
            results = [e for e in results if e.category == category]
        results.sort(key=lambda e: e.last_verified, reverse=True)
        return results

    async def get_context_for_llm(self, user_id: int, limit: int = 50) -> str:
        await self._ensure_initialized()
        entries = await self.get_entries(user_id)
        entries = entries[:limit]
        if not entries:
            return ""
        lines = [f"[{e.category}] {e.key}: {e.value}" for e in entries]
        return "\n".join(lines)

    async def get_entries_for_verification(
        self,
        user_id: int,
        low_confidence_threshold: float = 0.6,
        max_age_days: int = 90,
        max_entries: int = 5,
    ) -> list[KnowledgeEntry]:
        await self._ensure_initialized()
        from datetime import UTC, datetime, timedelta

        cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
        results = [
            e
            for e in self._entries.values()
            if e.user_id == user_id
            and e.deleted_at is None
            and (e.confidence < low_confidence_threshold or e.last_verified < cutoff)
        ]
        results.sort(key=lambda e: e.confidence)
        return results[:max_entries]

    async def find_contradicting_entry(
        self, user_id: int, category: str, key: str
    ) -> KnowledgeEntry | None:
        await self._ensure_initialized()
        for entry in self._entries.values():
            if (
                entry.user_id == user_id
                and entry.category == category
                and entry.key == key
                and entry.deleted_at is None
            ):
                return entry
        return None
