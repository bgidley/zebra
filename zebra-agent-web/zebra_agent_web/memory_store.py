"""Django ORM implementation for agent memory storage.

This module provides a Django-based storage backend for agent memory,
implementing the MemoryStore interface from zebra-agent.

Two-tier memory system:
- WorkflowMemoryModel: Detailed per-run records (zebra_workflow_memories table)
- ConceptualMemoryModel: Compact goal-pattern index (zebra_conceptual_memories table)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from asgiref.sync import sync_to_async
from zebra_agent.storage.interfaces import MemoryStore

from zebra_agent_web.middleware import get_current_user_id

if TYPE_CHECKING:
    from zebra_agent.memory import ConceptualMemoryEntry, WorkflowMemoryEntry

logger = logging.getLogger(__name__)


class DjangoMemoryStore(MemoryStore):
    """Django ORM implementation for agent memory storage.

    Provides the same interface as InMemoryMemoryStore but uses Django's
    ORM for database persistence across sessions.
    """

    def __init__(self) -> None:
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the store. Django handles schema via migrations."""
        self._initialized = True
        logger.info("DjangoMemoryStore initialized")

    async def close(self) -> None:
        """Close the store. Django manages connections automatically."""

    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            await self.initialize()

    # =========================================================================
    # Workflow Memory (Detailed per-run records)
    # =========================================================================

    async def add_workflow_memory(self, entry: WorkflowMemoryEntry) -> None:
        """Add a detailed workflow run record to memory."""
        await self._ensure_initialized()

        @sync_to_async
        def _add():
            from zebra_agent_web.api.models import WorkflowMemoryModel, WorkflowRunModel

            # Resolve user_id: request context first, then look up from run record
            user_id = get_current_user_id()
            if user_id is None and entry.run_id:
                try:
                    run_model = WorkflowRunModel.objects.get(id=entry.run_id)
                    user_id = run_model.user_id
                except WorkflowRunModel.DoesNotExist:
                    pass

            WorkflowMemoryModel.objects.update_or_create(
                id=entry.id,
                defaults={
                    "timestamp": entry.timestamp,
                    "workflow_name": entry.workflow_name,
                    "goal": entry.goal,
                    "success": entry.success,
                    "input_summary": entry.input_summary,
                    "output_summary": entry.output_summary,
                    "effectiveness_notes": entry.effectiveness_notes,
                    "tokens_used": entry.tokens_used,
                    "rating": entry.rating,
                    "user_feedback": entry.user_feedback,
                    "run_id": entry.run_id,
                    "model": entry.model,
                    "user_id": user_id,
                },
            )

        await _add()

    async def get_workflow_memories(
        self, workflow_name: str, limit: int = 10
    ) -> list[WorkflowMemoryEntry]:
        """Get recent memory entries for a specific workflow, newest first."""
        from zebra_agent.memory import WorkflowMemoryEntry as Entry

        await self._ensure_initialized()

        @sync_to_async
        def _get():
            from zebra_agent_web.api.models import WorkflowMemoryModel

            qs = WorkflowMemoryModel.objects.filter(workflow_name=workflow_name)
            uid = get_current_user_id()
            if uid is not None:
                qs = qs.filter(user_id=uid)
            qs = qs.order_by("-timestamp")[:limit]
            return [
                Entry(
                    id=m.id,
                    timestamp=m.timestamp,
                    workflow_name=m.workflow_name,
                    goal=m.goal,
                    success=m.success,
                    input_summary=m.input_summary,
                    output_summary=m.output_summary,
                    effectiveness_notes=m.effectiveness_notes,
                    tokens_used=m.tokens_used,
                    rating=m.rating,
                    user_feedback=m.user_feedback,
                    run_id=m.run_id,
                    model=m.model,
                )
                for m in qs
            ]

        return await _get()

    async def get_recent_workflow_memories(self, limit: int = 20) -> list[WorkflowMemoryEntry]:
        """Get the most recent workflow memory entries across all workflows."""
        from zebra_agent.memory import WorkflowMemoryEntry as Entry

        await self._ensure_initialized()

        @sync_to_async
        def _get():
            from zebra_agent_web.api.models import WorkflowMemoryModel

            qs = WorkflowMemoryModel.objects.all()
            uid = get_current_user_id()
            if uid is not None:
                qs = qs.filter(user_id=uid)
            qs = qs.order_by("-timestamp")[:limit]
            return [
                Entry(
                    id=m.id,
                    timestamp=m.timestamp,
                    workflow_name=m.workflow_name,
                    goal=m.goal,
                    success=m.success,
                    input_summary=m.input_summary,
                    output_summary=m.output_summary,
                    effectiveness_notes=m.effectiveness_notes,
                    tokens_used=m.tokens_used,
                    rating=m.rating,
                    user_feedback=m.user_feedback,
                    run_id=m.run_id,
                    model=m.model,
                )
                for m in qs
            ]

        return await _get()

    async def update_user_feedback(self, run_id: str, feedback: str) -> bool:
        """Update user feedback on the workflow memory entry for a run."""
        await self._ensure_initialized()

        @sync_to_async
        def _update():
            from zebra_agent_web.api.models import WorkflowMemoryModel

            updated = WorkflowMemoryModel.objects.filter(run_id=run_id).update(
                user_feedback=feedback
            )
            return updated > 0

        return await _update()

    # =========================================================================
    # Conceptual Memory (Compact goal-pattern index)
    # =========================================================================

    async def get_conceptual_memories(self, limit: int = 50) -> list[ConceptualMemoryEntry]:
        """Get all conceptual memory entries, most recently updated first."""
        from zebra_agent.memory import ConceptualMemoryEntry as Entry

        await self._ensure_initialized()

        @sync_to_async
        def _get():
            from zebra_agent_web.api.models import ConceptualMemoryModel

            qs = ConceptualMemoryModel.objects.all()
            uid = get_current_user_id()
            if uid is not None:
                qs = qs.filter(user_id=uid)
            qs = qs.order_by("-last_updated")[:limit]
            return [
                Entry(
                    id=m.id,
                    concept=m.concept,
                    recommended_workflows=m.recommended_workflows or [],
                    anti_patterns=m.anti_patterns or "",
                    last_updated=m.last_updated,
                    tokens=m.tokens,
                )
                for m in qs
            ]

        return await _get()

    async def save_conceptual_memory(self, entry: ConceptualMemoryEntry) -> None:
        """Save (insert or update) a conceptual memory entry."""
        await self._ensure_initialized()

        @sync_to_async
        def _save():
            from zebra_agent_web.api.models import ConceptualMemoryModel

            ConceptualMemoryModel.objects.update_or_create(
                id=entry.id,
                defaults={
                    "concept": entry.concept,
                    "recommended_workflows": entry.recommended_workflows,
                    "anti_patterns": entry.anti_patterns,
                    "last_updated": entry.last_updated,
                    "tokens": entry.tokens,
                    "user_id": get_current_user_id(),
                },
            )

        await _save()

    async def clear_conceptual_memories(self) -> None:
        """Remove all conceptual memory entries."""
        await self._ensure_initialized()

        @sync_to_async
        def _clear():
            from zebra_agent_web.api.models import ConceptualMemoryModel

            ConceptualMemoryModel.objects.all().delete()

        await _clear()

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

        @sync_to_async
        def _get_counts():
            from zebra_agent_web.api.models import ConceptualMemoryModel, WorkflowMemoryModel

            return {
                "workflow_memory_entries": WorkflowMemoryModel.objects.count(),
                "conceptual_memory_entries": ConceptualMemoryModel.objects.count(),
            }

        return await _get_counts()
