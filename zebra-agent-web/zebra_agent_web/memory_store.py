"""Django ORM implementation for agent memory storage.

This module provides a Django-based storage backend for agent memory,
implementing the MemoryStore interface from zebra-agent.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from asgiref.sync import sync_to_async

from zebra_agent.storage.interfaces import MemoryStore

from .api.models import LongTermThemeModel, MemoryEntryModel, ShortTermSummaryModel

if TYPE_CHECKING:
    from zebra_agent.memory import LongTermTheme, MemoryEntry, ShortTermSummary

logger = logging.getLogger(__name__)


class DjangoMemoryStore(MemoryStore):
    """Django ORM implementation for agent memory storage.

    Provides the same interface as InMemoryMemoryStore but uses Django's
    ORM for database persistence.
    """

    def __init__(
        self,
        short_term_max_tokens: int = 20000,
        long_term_max_tokens: int = 30000,
        compact_threshold: float = 0.9,
    ):
        self._short_term_max_tokens = short_term_max_tokens
        self._long_term_max_tokens = long_term_max_tokens
        self._compact_threshold = compact_threshold
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the store. Django handles schema via migrations."""
        self._initialized = True
        logger.info("DjangoMemoryStore initialized")

    async def close(self) -> None:
        """Close the store. Django manages connections automatically."""
        pass

    async def _ensure_initialized(self) -> None:
        """Ensure the store is initialized."""
        if not self._initialized:
            await self.initialize()

    # =========================================================================
    # Short-Term Memory Operations
    # =========================================================================

    async def add_entry(self, entry: MemoryEntry) -> None:
        """Add a memory entry to short-term storage."""
        await self._ensure_initialized()

        @sync_to_async
        def _add():
            MemoryEntryModel.objects.update_or_create(
                id=entry.id,
                defaults={
                    "timestamp": entry.timestamp,
                    "goal": entry.goal,
                    "workflow_used": entry.workflow_used,
                    "result_summary": entry.result_summary,
                    "tokens": entry.tokens,
                },
            )

        await _add()

    async def get_short_term_entries(self, limit: int | None = None) -> list[MemoryEntry]:
        """Get recent entries, ordered by timestamp descending (newest first)."""
        from zebra_agent.memory import MemoryEntry

        await self._ensure_initialized()

        @sync_to_async
        def _get():
            queryset = MemoryEntryModel.objects.all().order_by("-timestamp")
            if limit is not None:
                queryset = queryset[:limit]
            return [
                MemoryEntry(
                    id=m.id,
                    timestamp=m.timestamp,
                    goal=m.goal,
                    workflow_used=m.workflow_used,
                    result_summary=m.result_summary,
                    tokens=m.tokens,
                )
                for m in queryset
            ]

        return await _get()

    async def get_short_term_tokens(self) -> int:
        """Get total token count of all short-term entries."""
        await self._ensure_initialized()

        @sync_to_async
        def _get():
            from django.db.models import Sum

            result = MemoryEntryModel.objects.aggregate(total=Sum("tokens"))
            return result["total"] or 0

        return await _get()

    async def get_short_term_summary_tokens(self) -> int:
        """Get total token count of all short-term summaries."""
        await self._ensure_initialized()

        @sync_to_async
        def _get():
            from django.db.models import Sum

            result = ShortTermSummaryModel.objects.aggregate(total=Sum("tokens"))
            return result["total"] or 0

        return await _get()

    async def needs_short_term_compaction(self) -> bool:
        """Check if short-term memory needs compaction (above threshold)."""
        await self._ensure_initialized()
        total_tokens = await self.get_short_term_tokens()
        threshold = self._short_term_max_tokens * self._compact_threshold
        return total_tokens >= threshold

    async def get_short_term_summaries(self, limit: int | None = None) -> list[ShortTermSummary]:
        """Get short-term summaries, ordered by creation time descending."""
        from zebra_agent.memory import ShortTermSummary

        await self._ensure_initialized()

        @sync_to_async
        def _get():
            queryset = ShortTermSummaryModel.objects.all().order_by("-created_at")
            if limit is not None:
                queryset = queryset[:limit]
            return [
                ShortTermSummary(
                    id=m.id,
                    created_at=m.created_at,
                    summary=m.summary,
                    tokens=m.tokens,
                    entry_count=m.entry_count,
                )
                for m in queryset
            ]

        return await _get()

    async def get_short_term_summary_by_id(self, summary_id: str) -> ShortTermSummary | None:
        """Get a specific short-term summary by ID."""
        from zebra_agent.memory import ShortTermSummary

        await self._ensure_initialized()

        @sync_to_async
        def _get():
            try:
                m = ShortTermSummaryModel.objects.get(id=summary_id)
                return ShortTermSummary(
                    id=m.id,
                    created_at=m.created_at,
                    summary=m.summary,
                    tokens=m.tokens,
                    entry_count=m.entry_count,
                )
            except ShortTermSummaryModel.DoesNotExist:
                return None

        return await _get()

    async def add_short_term_summary(self, summary: ShortTermSummary) -> None:
        """Add a compacted summary to short-term storage."""
        await self._ensure_initialized()

        @sync_to_async
        def _add():
            ShortTermSummaryModel.objects.update_or_create(
                id=summary.id,
                defaults={
                    "created_at": summary.created_at,
                    "summary": summary.summary,
                    "tokens": summary.tokens,
                    "entry_count": summary.entry_count,
                },
            )

        await _add()

    async def clear_short_term_entries(self) -> None:
        """Clear all short-term entries (after compaction)."""
        await self._ensure_initialized()

        @sync_to_async
        def _clear():
            MemoryEntryModel.objects.all().delete()

        await _clear()

    async def get_short_term_content_for_compaction(self) -> str:
        """Format entries as text for LLM compaction."""
        await self._ensure_initialized()
        entries = await self.get_short_term_entries()
        lines = []
        for entry in entries:
            lines.append(f"[{entry.timestamp.isoformat()}]")
            lines.append(f"Goal: {entry.goal}")
            lines.append(f"Workflow: {entry.workflow_used}")
            lines.append(f"Result: {entry.result_summary}")
            lines.append("")
        return "\n".join(lines)

    # =========================================================================
    # Long-Term Memory Operations
    # =========================================================================

    async def get_long_term_tokens(self) -> int:
        """Get total token count of all long-term themes."""
        await self._ensure_initialized()

        @sync_to_async
        def _get():
            from django.db.models import Sum

            result = LongTermThemeModel.objects.aggregate(total=Sum("tokens"))
            return result["total"] or 0

        return await _get()

    async def needs_long_term_compaction(self) -> bool:
        """Check if long-term memory needs compaction (above threshold)."""
        await self._ensure_initialized()
        summary_tokens = await self.get_short_term_summary_tokens()
        theme_tokens = await self.get_long_term_tokens()
        total_tokens = summary_tokens + theme_tokens
        threshold = self._long_term_max_tokens * self._compact_threshold
        return total_tokens >= threshold

    async def get_long_term_themes(self, limit: int | None = None) -> list[LongTermTheme]:
        """Get long-term themes, ordered by creation time descending."""
        from zebra_agent.memory import LongTermTheme

        await self._ensure_initialized()

        @sync_to_async
        def _get():
            queryset = LongTermThemeModel.objects.all().order_by("-created_at")
            if limit is not None:
                queryset = queryset[:limit]
            return [
                LongTermTheme(
                    id=m.id,
                    created_at=m.created_at,
                    theme=m.theme,
                    tokens=m.tokens,
                    short_term_refs=m.short_term_refs or [],
                )
                for m in queryset
            ]

        return await _get()

    async def add_long_term_theme(self, theme: LongTermTheme) -> None:
        """Add a theme to long-term storage."""
        await self._ensure_initialized()

        @sync_to_async
        def _add():
            LongTermThemeModel.objects.update_or_create(
                id=theme.id,
                defaults={
                    "created_at": theme.created_at,
                    "theme": theme.theme,
                    "tokens": theme.tokens,
                    "short_term_refs": theme.short_term_refs,
                },
            )

        await _add()

    async def clear_short_term_summaries(self, keep_ids: list[str] | None = None) -> None:
        """Clear short-term summaries, optionally keeping specified IDs."""
        await self._ensure_initialized()

        @sync_to_async
        def _clear():
            if keep_ids:
                ShortTermSummaryModel.objects.exclude(id__in=keep_ids).delete()
            else:
                ShortTermSummaryModel.objects.all().delete()

        await _clear()

    async def get_long_term_content_for_compaction(self) -> str:
        """Format themes and summaries as text for LLM compaction."""
        await self._ensure_initialized()
        lines = []

        # Add existing themes
        themes = await self.get_long_term_themes()
        if themes:
            lines.append("## Existing Themes")
            for theme in themes:
                lines.append(f"- {theme.theme}")
            lines.append("")

        # Add summaries to be processed
        summaries = await self.get_short_term_summaries()
        if summaries:
            lines.append("## Recent Summaries")
            for summary in summaries:
                lines.append(f"[{summary.created_at.isoformat()}]")
                lines.append(summary.summary)
                lines.append("")

        return "\n".join(lines)

    async def get_details_for_theme(self, theme: LongTermTheme) -> str:
        """Get detailed summary content referenced by a theme."""
        await self._ensure_initialized()
        lines = []
        for ref_id in theme.short_term_refs:
            summary = await self.get_short_term_summary_by_id(ref_id)
            if summary:
                lines.append(summary.summary)
        return "\n\n".join(lines)

    # =========================================================================
    # Context Generation
    # =========================================================================

    async def get_context_for_llm(self) -> str:
        """Build context string for LLM (themes + summaries + entries)."""
        await self._ensure_initialized()
        sections = []

        # Long-term themes
        themes = await self.get_long_term_themes()
        if themes:
            theme_lines = ["## Long-term Memory (Themes)"]
            for theme in themes:
                theme_lines.append(f"- {theme.theme}")
            sections.append("\n".join(theme_lines))

        # Short-term summaries
        summaries = await self.get_short_term_summaries()
        if summaries:
            summary_lines = ["## Short-term Memory (Summaries)"]
            for summary in summaries:
                summary_lines.append(f"[{summary.created_at.isoformat()}]")
                summary_lines.append(summary.summary)
                summary_lines.append("")
            sections.append("\n".join(summary_lines))

        # Recent entries
        entries = await self.get_short_term_entries(limit=10)
        if entries:
            entry_lines = ["## Recent Interactions"]
            for entry in entries:
                entry_lines.append(f"[{entry.timestamp.isoformat()}]")
                entry_lines.append(f"Goal: {entry.goal}")
                entry_lines.append(f"Workflow: {entry.workflow_used}")
                entry_lines.append(f"Result: {entry.result_summary}")
                entry_lines.append("")
            sections.append("\n".join(entry_lines))

        return "\n\n".join(sections) if sections else ""

    async def get_stats(self) -> dict:
        """Return memory statistics."""
        await self._ensure_initialized()

        entries = await self.get_short_term_entries()
        summaries = await self.get_short_term_summaries()
        themes = await self.get_long_term_themes()

        return {
            "short_term_entries": len(entries),
            "short_term_tokens": await self.get_short_term_tokens(),
            "short_term_max_tokens": self._short_term_max_tokens,
            "short_term_summaries": len(summaries),
            "short_term_summary_tokens": await self.get_short_term_summary_tokens(),
            "long_term_themes": len(themes),
            "long_term_tokens": await self.get_long_term_tokens(),
            "long_term_max_tokens": self._long_term_max_tokens,
            "compact_threshold": self._compact_threshold,
        }
