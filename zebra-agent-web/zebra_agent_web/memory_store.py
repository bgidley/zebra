"""Django ORM implementation for agent memory storage.

This module provides a Django-based storage backend for agent memory,
implementing the MemoryStore interface from zebra-agent.

Two-tier memory system:
- WorkflowMemoryModel: Detailed per-run records (zebra_workflow_memories table)
- ConceptualMemoryModel: Compact goal-pattern index (zebra_conceptual_memories table)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from asgiref.sync import sync_to_async
from django.db import IntegrityError, transaction
from zebra_agent.storage.interfaces import CompactionBatch, MemoryStore, format_conceptual_context

from zebra_agent_web.middleware import get_current_user_id

if TYPE_CHECKING:
    from zebra_agent.memory import ConceptualMemoryEntry, PostmortemEntry, WorkflowMemoryEntry

logger = logging.getLogger(__name__)


def _nearest_ids(table: str, goal: str, limit: int) -> list[str] | None:
    """Ids nearest to ``goal`` for the current user, or None to use the fallback (#169)."""
    from zebra_agent_web import embeddings

    if not goal or not goal.strip() or not embeddings.vector_search_ready():
        return None
    uid = get_current_user_id()
    # Bind names must not be Oracle reserved words (UID → ORA-01745).
    where, params = (
        ("t.user_id = %(owner_id)s", {"owner_id": uid}) if uid is not None else ("", None)
    )
    try:
        return embeddings.nearest_ids(table, goal, limit, where=where, params=params)
    except Exception as e:  # noqa: BLE001 - retrieval must degrade, not fail the goal
        logger.warning("Vector search on %s failed, using keyword ranking: %s", table, e)
        return None


def _to_workflow_entry(m) -> WorkflowMemoryEntry:  # type: ignore[no-untyped-def]
    from zebra_agent.memory import WorkflowMemoryEntry as Entry

    return Entry(
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
        tier=m.tier,
    )


def _to_conceptual_entry(m) -> ConceptualMemoryEntry:  # type: ignore[no-untyped-def]
    from zebra_agent.memory import ConceptualMemoryEntry as Entry

    return Entry(
        id=m.id,
        concept=m.concept,
        recommended_workflows=m.recommended_workflows or [],
        anti_patterns=m.anti_patterns or "",
        last_updated=m.last_updated,
        tokens=m.tokens,
        tier=m.tier,
    )


def _to_postmortem(m) -> PostmortemEntry:  # type: ignore[no-untyped-def]
    from zebra_agent.memory import PostmortemEntry as Entry

    return Entry(
        id=m.id,
        timestamp=m.timestamp,
        run_id=m.run_id or "",
        goal=m.goal,
        workflow_name=m.workflow_name,
        trigger=m.trigger,
        what_happened=m.what_happened,
        root_cause=m.root_cause,
        lesson=m.lesson,
        voice=m.voice,
        confidence=m.confidence,
        user_id=m.user_id,
    )


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

        @sync_to_async(thread_sensitive=False)
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
                    "tier": entry.tier,
                    "user_id": user_id,
                },
            )

        await _add()

    async def get_workflow_memories(
        self, workflow_name: str, limit: int = 10
    ) -> list[WorkflowMemoryEntry]:
        """Get recent memory entries for a specific workflow, newest first."""
        await self._ensure_initialized()

        @sync_to_async(thread_sensitive=False)
        def _get():
            from zebra_agent_web.api.models import WorkflowMemoryModel

            qs = WorkflowMemoryModel.objects.filter(workflow_name=workflow_name)
            uid = get_current_user_id()
            if uid is not None:
                qs = qs.filter(user_id=uid)
            qs = qs.order_by("-timestamp")[:limit]
            return [_to_workflow_entry(m) for m in qs]

        return await _get()

    async def get_recent_workflow_memories(self, limit: int = 20) -> list[WorkflowMemoryEntry]:
        """Get the most recent workflow memory entries across all workflows."""
        await self._ensure_initialized()

        @sync_to_async(thread_sensitive=False)
        def _get():
            from zebra_agent_web.api.models import WorkflowMemoryModel

            qs = WorkflowMemoryModel.objects.all()
            uid = get_current_user_id()
            if uid is not None:
                qs = qs.filter(user_id=uid)
            qs = qs.order_by("-timestamp")[:limit]
            return [_to_workflow_entry(m) for m in qs]

        return await _get()

    async def update_user_feedback(self, run_id: str, feedback: str) -> bool:
        """Update user feedback on the workflow memory entry for a run."""
        await self._ensure_initialized()

        @sync_to_async(thread_sensitive=False)
        def _update():
            from zebra_agent_web.api.models import WorkflowMemoryModel

            updated = WorkflowMemoryModel.objects.filter(run_id=run_id).update(
                user_feedback=feedback
            )
            return updated > 0

        return await _update()

    async def get_workflow_memory_by_run_id(self, run_id: str) -> WorkflowMemoryEntry | None:
        """Return the workflow memory entry for a specific run, or None if not found."""
        await self._ensure_initialized()

        @sync_to_async(thread_sensitive=False)
        def _get():
            from zebra_agent_web.api.models import WorkflowMemoryModel

            m = WorkflowMemoryModel.objects.filter(run_id=run_id).first()
            if m is None:
                return None
            return _to_workflow_entry(m)

        return await _get()

    # =========================================================================
    # Conceptual Memory (Compact goal-pattern index)
    # =========================================================================

    async def get_conceptual_memories(self, limit: int = 50) -> list[ConceptualMemoryEntry]:
        """Get all conceptual memory entries, most recently updated first."""
        await self._ensure_initialized()

        @sync_to_async(thread_sensitive=False)
        def _get():
            from zebra_agent_web.api.models import ConceptualMemoryModel

            qs = ConceptualMemoryModel.objects.all()
            uid = get_current_user_id()
            if uid is not None:
                qs = qs.filter(user_id=uid)
            qs = qs.order_by("-last_updated")[:limit]
            return [_to_conceptual_entry(m) for m in qs]

        return await _get()

    async def save_conceptual_memory(self, entry: ConceptualMemoryEntry) -> None:
        """Save (insert or update) a conceptual memory entry."""
        await self._ensure_initialized()

        @sync_to_async(thread_sensitive=False)
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
                    "tier": entry.tier,
                    "user_id": get_current_user_id(),
                },
            )

        await _save()

    async def clear_conceptual_memories(self) -> None:
        """Remove all conceptual memory entries."""
        await self._ensure_initialized()

        @sync_to_async(thread_sensitive=False)
        def _clear():
            from zebra_agent_web.api.models import ConceptualMemoryModel

            ConceptualMemoryModel.objects.all().delete()

        await _clear()

    # =========================================================================
    # Goal-relevant retrieval (#169)
    # =========================================================================

    async def search_conceptual_memories(
        self, goal: str, limit: int = 10
    ) -> list[ConceptualMemoryEntry]:
        """Conceptual memories nearest to the goal by in-database embedding (Oracle).

        Falls back to keyword ranking when vector search is unavailable or fails.
        """
        await self._ensure_initialized()

        @sync_to_async(thread_sensitive=False)
        def _search():
            from zebra_agent_web.api.models import ConceptualMemoryModel

            ids = _nearest_ids("zebra_conceptual_memories", goal, limit)
            if ids is None:
                return None
            rows = {m.id: m for m in ConceptualMemoryModel.objects.filter(id__in=ids)}
            return [_to_conceptual_entry(rows[i]) for i in ids if i in rows]

        found = await _search()
        if found is None:
            return await super().search_conceptual_memories(goal, limit)
        return found

    async def search_workflow_memories(
        self, goal: str, limit: int = 5
    ) -> list[WorkflowMemoryEntry]:
        """Past runs whose goals are nearest to this goal by embedding (Oracle).

        Falls back to keyword ranking when vector search is unavailable or fails.
        """
        await self._ensure_initialized()

        @sync_to_async(thread_sensitive=False)
        def _search():
            from zebra_agent_web.api.models import WorkflowMemoryModel

            ids = _nearest_ids("zebra_workflow_memories", goal, limit)
            if ids is None:
                return None
            rows = {m.id: m for m in WorkflowMemoryModel.objects.filter(id__in=ids)}
            return [_to_workflow_entry(rows[i]) for i in ids if i in rows]

        found = await _search()
        if found is None:
            return await super().search_workflow_memories(goal, limit)
        return found

    # =========================================================================
    # Postmortem journal (#175)
    # =========================================================================

    async def add_postmortem(self, entry: PostmortemEntry) -> None:
        """Store a postmortem, owned by its user_id, else the request user, else the run's."""
        await self._ensure_initialized()

        @sync_to_async(thread_sensitive=False)
        def _add():
            from zebra_agent_web.api.models import PostmortemModel, WorkflowRunModel

            user_id = entry.user_id if entry.user_id is not None else get_current_user_id()
            if user_id is None and entry.run_id:
                run = WorkflowRunModel.objects.filter(id=entry.run_id).first()
                user_id = run.user_id if run is not None else None

            if entry.run_id and PostmortemModel.objects.filter(run_id=entry.run_id).exists():
                logger.info("Run %s already has a postmortem; keeping it", entry.run_id)
                return
            try:
                with transaction.atomic():
                    _save(PostmortemModel, user_id)
            except IntegrityError:
                # Another trigger stored this run's postmortem first (#175).
                logger.info("Run %s already has a postmortem; keeping it", entry.run_id)

        def _save(PostmortemModel, user_id):  # noqa: N803
            PostmortemModel.objects.update_or_create(
                id=entry.id,
                defaults={
                    "user_id": user_id,
                    "timestamp": entry.timestamp,
                    "run_id": entry.run_id or None,
                    "goal": entry.goal,
                    "workflow_name": entry.workflow_name,
                    "trigger": entry.trigger,
                    "what_happened": entry.what_happened,
                    "root_cause": entry.root_cause,
                    "lesson": entry.lesson,
                    "voice": entry.voice,
                    "confidence": entry.confidence,
                },
            )

        await _add()

    async def get_recent_postmortems(self, limit: int = 50) -> list[PostmortemEntry]:
        """Return the current user's most recent postmortems, newest first."""
        await self._ensure_initialized()

        @sync_to_async(thread_sensitive=False)
        def _get():
            from zebra_agent_web.api.models import PostmortemModel

            qs = PostmortemModel.objects.all()
            uid = get_current_user_id()
            if uid is not None:
                qs = qs.filter(user_id=uid)
            return [_to_postmortem(m) for m in qs.order_by("-timestamp")[:limit]]

        return await _get()

    async def get_postmortem_by_run_id(self, run_id: str) -> PostmortemEntry | None:
        """Return the postmortem written for a run, or None."""
        await self._ensure_initialized()

        @sync_to_async(thread_sensitive=False)
        def _get():
            from zebra_agent_web.api.models import PostmortemModel

            m = PostmortemModel.objects.filter(run_id=run_id).first()
            return _to_postmortem(m) if m is not None else None

        return await _get()

    async def search_postmortems(self, goal: str, limit: int = 3) -> list[PostmortemEntry]:
        """Postmortems whose goals are nearest to this goal by embedding (Oracle).

        Falls back to keyword matching when vector search is unavailable or fails.
        """
        await self._ensure_initialized()

        @sync_to_async(thread_sensitive=False)
        def _search():
            from zebra_agent_web.api.models import PostmortemModel

            ids = _nearest_ids("zebra_postmortems", goal, limit)
            if ids is None:
                return None
            rows = {m.id: m for m in PostmortemModel.objects.filter(id__in=ids)}
            return [_to_postmortem(rows[i]) for i in ids if i in rows]

        found = await _search()
        if found is None:
            return await super().search_postmortems(goal, limit)
        return found

    # =========================================================================
    # Context Generation
    # =========================================================================

    async def get_conceptual_context_for_llm(self) -> str:
        """Format conceptual memory as a context string for the LLM."""
        await self._ensure_initialized()
        return format_conceptual_context(await self.get_conceptual_memories())

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

        @sync_to_async(thread_sensitive=False)
        def _get_counts():
            from zebra_agent_web.api.models import ConceptualMemoryModel, WorkflowMemoryModel

            return {
                "workflow_memory_entries": WorkflowMemoryModel.objects.count(),
                "conceptual_memory_entries": ConceptualMemoryModel.objects.count(),
            }

        return await _get_counts()

    # =========================================================================
    # Compaction (Tiered retention)
    # =========================================================================

    async def get_entries_for_compaction(self, now: datetime) -> CompactionBatch:
        """Return entries that have crossed a tier boundary since last compaction."""
        from datetime import timedelta

        await self._ensure_initialized()
        warm_cutoff = now - timedelta(weeks=2)
        cold_cutoff = now - timedelta(days=60)

        @sync_to_async(thread_sensitive=False)
        def _query():
            from zebra_agent_web.api.models import ConceptualMemoryModel, WorkflowMemoryModel

            warm_wf = WorkflowMemoryModel.objects.filter(
                timestamp__lte=warm_cutoff, tier="hot"
            ).exclude(timestamp__lte=cold_cutoff)
            cold_wf = WorkflowMemoryModel.objects.filter(timestamp__lte=cold_cutoff).exclude(
                tier="cold"
            )
            warm_cm = ConceptualMemoryModel.objects.filter(
                last_updated__lte=warm_cutoff, tier="hot"
            ).exclude(last_updated__lte=cold_cutoff)
            cold_cm = ConceptualMemoryModel.objects.filter(last_updated__lte=cold_cutoff).exclude(
                tier="cold"
            )

            return CompactionBatch(
                warm_workflow=[_to_workflow_entry(m) for m in warm_wf],
                cold_workflow=[_to_workflow_entry(m) for m in cold_wf],
                warm_conceptual=[_to_conceptual_entry(m) for m in warm_cm],
                cold_conceptual=[_to_conceptual_entry(m) for m in cold_cm],
            )

        return await _query()

    async def update_workflow_memory_tier(
        self,
        entry_id: str,
        tier: str,
        output_summary: str | None = None,
        effectiveness_notes: str | None = None,
    ) -> None:
        """Update tier and optionally compressed fields on a WorkflowMemoryEntry."""
        await self._ensure_initialized()

        @sync_to_async(thread_sensitive=False)
        def _update():
            from zebra_agent_web.api.models import WorkflowMemoryModel

            updates: dict = {"tier": tier}
            if output_summary is not None:
                updates["output_summary"] = output_summary
            if effectiveness_notes is not None:
                updates["effectiveness_notes"] = effectiveness_notes
            WorkflowMemoryModel.objects.filter(id=entry_id).update(**updates)

        await _update()

    async def update_conceptual_memory_tier(
        self,
        entry_id: str,
        tier: str,
        recommended_workflows: list[dict] | None = None,
        anti_patterns: str | None = None,
    ) -> None:
        """Update tier and optionally trimmed fields on a ConceptualMemoryEntry."""
        await self._ensure_initialized()

        @sync_to_async(thread_sensitive=False)
        def _update():
            from zebra_agent_web.api.models import ConceptualMemoryModel

            updates: dict = {"tier": tier}
            if recommended_workflows is not None:
                updates["recommended_workflows"] = recommended_workflows
            if anti_patterns is not None:
                updates["anti_patterns"] = anti_patterns
            ConceptualMemoryModel.objects.filter(id=entry_id).update(**updates)

        await _update()
