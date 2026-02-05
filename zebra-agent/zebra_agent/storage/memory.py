"""In-memory implementation of the MemoryStore interface.

This module provides a pure Python in-memory storage backend for agent memory.
Data is lost when the process exits - suitable for testing and ephemeral use cases.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from zebra_agent.storage.interfaces import MemoryStore

if TYPE_CHECKING:
    from zebra_agent.memory import LongTermTheme, MemoryEntry, ShortTermSummary

logger = logging.getLogger(__name__)


class InMemoryMemoryStore(MemoryStore):
    """In-memory implementation of agent memory storage.

    Stores all data in Python lists. Data is not persisted.

    Args:
        short_term_max_tokens: Maximum tokens for short-term memory (default 20000)
        long_term_max_tokens: Maximum tokens for long-term memory (default 30000)
        compact_threshold: Fraction of max tokens to trigger compaction (default 0.9)
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

        self._entries: list[MemoryEntry] = []
        self._summaries: list[ShortTermSummary] = []
        self._themes: list[LongTermTheme] = []
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the memory store."""
        self._initialized = True
        logger.info("InMemoryMemoryStore initialized")

    async def close(self) -> None:
        """Close the memory store."""
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
        self._entries.append(entry)
        # Keep sorted by timestamp descending
        self._entries.sort(key=lambda e: e.timestamp, reverse=True)

    async def get_short_term_entries(self, limit: int | None = None) -> list[MemoryEntry]:
        """Get recent entries, ordered by timestamp descending (newest first)."""
        await self._ensure_initialized()
        entries = self._entries
        if limit is not None:
            entries = entries[:limit]
        return list(entries)

    async def get_short_term_tokens(self) -> int:
        """Get total token count of all short-term entries."""
        await self._ensure_initialized()
        return sum(e.tokens for e in self._entries)

    async def get_short_term_summary_tokens(self) -> int:
        """Get total token count of all short-term summaries."""
        await self._ensure_initialized()
        return sum(s.tokens for s in self._summaries)

    async def needs_short_term_compaction(self) -> bool:
        """Check if short-term memory needs compaction (above threshold)."""
        await self._ensure_initialized()
        total_tokens = await self.get_short_term_tokens()
        threshold = self._short_term_max_tokens * self._compact_threshold
        return total_tokens >= threshold

    async def get_short_term_summaries(self, limit: int | None = None) -> list[ShortTermSummary]:
        """Get short-term summaries, ordered by creation time descending."""
        await self._ensure_initialized()
        summaries = self._summaries
        if limit is not None:
            summaries = summaries[:limit]
        return list(summaries)

    async def get_short_term_summary_by_id(self, summary_id: str) -> ShortTermSummary | None:
        """Get a specific short-term summary by ID."""
        await self._ensure_initialized()
        for s in self._summaries:
            if s.id == summary_id:
                return s
        return None

    async def add_short_term_summary(self, summary: ShortTermSummary) -> None:
        """Add a compacted summary to short-term storage."""
        await self._ensure_initialized()
        self._summaries.append(summary)
        # Keep sorted by created_at descending
        self._summaries.sort(key=lambda s: s.created_at, reverse=True)

    async def clear_short_term_entries(self) -> None:
        """Clear all short-term entries (after compaction)."""
        await self._ensure_initialized()
        self._entries.clear()

    async def get_short_term_content_for_compaction(self) -> str:
        """Format entries as text for LLM compaction."""
        await self._ensure_initialized()
        lines = []
        for entry in self._entries:
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
        return sum(t.tokens for t in self._themes)

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
        await self._ensure_initialized()
        themes = self._themes
        if limit is not None:
            themes = themes[:limit]
        return list(themes)

    async def add_long_term_theme(self, theme: LongTermTheme) -> None:
        """Add a theme to long-term storage."""
        await self._ensure_initialized()
        self._themes.append(theme)
        # Keep sorted by created_at descending
        self._themes.sort(key=lambda t: t.created_at, reverse=True)

    async def clear_short_term_summaries(self, keep_ids: list[str] | None = None) -> None:
        """Clear short-term summaries, optionally keeping specified IDs."""
        await self._ensure_initialized()
        if keep_ids is None:
            self._summaries.clear()
        else:
            self._summaries = [s for s in self._summaries if s.id in keep_ids]

    async def get_long_term_content_for_compaction(self) -> str:
        """Format themes and summaries as text for LLM compaction."""
        await self._ensure_initialized()
        lines = []

        # Add existing themes
        if self._themes:
            lines.append("## Existing Themes")
            for theme in self._themes:
                lines.append(f"- {theme.theme}")
            lines.append("")

        # Add summaries to be processed
        if self._summaries:
            lines.append("## Recent Summaries")
            for summary in self._summaries:
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
        if self._themes:
            theme_lines = ["## Long-term Memory (Themes)"]
            for theme in self._themes:
                theme_lines.append(f"- {theme.theme}")
            sections.append("\n".join(theme_lines))

        # Short-term summaries
        if self._summaries:
            summary_lines = ["## Short-term Memory (Summaries)"]
            for summary in self._summaries:
                summary_lines.append(f"[{summary.created_at.isoformat()}]")
                summary_lines.append(summary.summary)
                summary_lines.append("")
            sections.append("\n".join(summary_lines))

        # Recent entries
        if self._entries:
            entry_lines = ["## Recent Interactions"]
            for entry in self._entries[:10]:  # Limit to 10 most recent
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
        return {
            "short_term_entries": len(self._entries),
            "short_term_tokens": await self.get_short_term_tokens(),
            "short_term_max_tokens": self._short_term_max_tokens,
            "short_term_summaries": len(self._summaries),
            "short_term_summary_tokens": await self.get_short_term_summary_tokens(),
            "long_term_themes": len(self._themes),
            "long_term_tokens": await self.get_long_term_tokens(),
            "long_term_max_tokens": self._long_term_max_tokens,
            "compact_threshold": self._compact_threshold,
        }
