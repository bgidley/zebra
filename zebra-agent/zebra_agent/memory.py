"""Local memory for agent conversations with short-term and long-term storage."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite


@dataclass
class MemoryEntry:
    """A single memory entry."""

    id: str
    timestamp: datetime
    goal: str
    workflow_used: str
    result_summary: str
    tokens: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "goal": self.goal,
            "workflow_used": self.workflow_used,
            "result_summary": self.result_summary,
            "tokens": self.tokens,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryEntry":
        return cls(
            id=data["id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            goal=data["goal"],
            workflow_used=data["workflow_used"],
            result_summary=data["result_summary"],
            tokens=data["tokens"],
        )


@dataclass
class ShortTermSummary:
    """A compacted short-term memory summary."""

    id: str
    created_at: datetime
    summary: str
    tokens: int
    entry_count: int  # How many entries were summarized


@dataclass
class LongTermTheme:
    """A long-term memory theme."""

    id: str
    created_at: datetime
    theme: str
    tokens: int
    short_term_refs: list[str]  # IDs of short-term summaries this references


class AgentMemory:
    """
    Agent memory with short-term and long-term storage.

    Short-term memory:
    - Stores recent interaction details
    - Compacts into detailed summaries
    - Focus: specific facts, outcomes, recent context

    Long-term memory:
    - Stores themes and patterns from short-term summaries
    - Compacts into thematic summaries
    - Focus: user preferences, recurring patterns, learned insights
    - References short-term summaries for details
    """

    def __init__(
        self,
        db_path: str | Path,
        short_term_max_tokens: int = 20000,
        long_term_max_tokens: int = 30000,
        compact_threshold: float = 0.9,
    ):
        """
        Initialize agent memory.

        Args:
            db_path: Path to SQLite database
            short_term_max_tokens: Max tokens for short-term memory
            long_term_max_tokens: Max tokens for long-term memory
            compact_threshold: Trigger compaction at this fraction of max
        """
        self.db_path = Path(db_path).expanduser()
        self.short_term_max_tokens = short_term_max_tokens
        self.long_term_max_tokens = long_term_max_tokens
        self.compact_threshold = compact_threshold
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        """Ensure database tables exist."""
        if self._initialized:
            return

        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(
                """
                -- Short-term: individual interaction entries
                CREATE TABLE IF NOT EXISTS short_term_entries (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    workflow_used TEXT,
                    result_summary TEXT,
                    tokens INTEGER DEFAULT 0
                );

                -- Short-term: compacted summaries (detail-focused)
                CREATE TABLE IF NOT EXISTS short_term_summaries (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    tokens INTEGER DEFAULT 0,
                    entry_count INTEGER DEFAULT 0
                );

                -- Long-term: thematic summaries
                CREATE TABLE IF NOT EXISTS long_term_themes (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    theme TEXT NOT NULL,
                    tokens INTEGER DEFAULT 0,
                    short_term_refs TEXT  -- JSON array of short_term_summary IDs
                );

                -- State tracking
                CREATE TABLE IF NOT EXISTS memory_state (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_short_term_timestamp
                ON short_term_entries(timestamp);

                CREATE INDEX IF NOT EXISTS idx_short_term_summary_created
                ON short_term_summaries(created_at);

                CREATE INDEX IF NOT EXISTS idx_long_term_created
                ON long_term_themes(created_at);
                """
            )
            await db.commit()

        self._initialized = True

    # ==================== Short-Term Memory ====================

    async def add_entry(self, entry: MemoryEntry) -> None:
        """Add an entry to short-term memory."""
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO short_term_entries
                (id, timestamp, goal, workflow_used, result_summary, tokens)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.id,
                    entry.timestamp.isoformat(),
                    entry.goal,
                    entry.workflow_used,
                    entry.result_summary,
                    entry.tokens,
                ),
            )
            await db.commit()

    async def get_short_term_entries(self, limit: int | None = None) -> list[MemoryEntry]:
        """Get short-term entries, most recent first."""
        await self._ensure_initialized()

        entries = []
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = "SELECT * FROM short_term_entries ORDER BY timestamp DESC"
            if limit:
                query += f" LIMIT {limit}"

            async with db.execute(query) as cursor:
                async for row in cursor:
                    entries.append(
                        MemoryEntry(
                            id=row["id"],
                            timestamp=datetime.fromisoformat(row["timestamp"]),
                            goal=row["goal"],
                            workflow_used=row["workflow_used"] or "",
                            result_summary=row["result_summary"] or "",
                            tokens=row["tokens"] or 0,
                        )
                    )

        return entries

    async def get_short_term_tokens(self) -> int:
        """Get total tokens in short-term entries."""
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COALESCE(SUM(tokens), 0) FROM short_term_entries"
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def get_short_term_summary_tokens(self) -> int:
        """Get total tokens in short-term summaries."""
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COALESCE(SUM(tokens), 0) FROM short_term_summaries"
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def needs_short_term_compaction(self) -> bool:
        """Check if short-term memory needs compaction."""
        total = await self.get_short_term_tokens()
        threshold = int(self.short_term_max_tokens * self.compact_threshold)
        return total >= threshold

    async def get_short_term_summaries(self, limit: int | None = None) -> list[ShortTermSummary]:
        """Get short-term summaries, most recent first."""
        await self._ensure_initialized()

        summaries = []
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = "SELECT * FROM short_term_summaries ORDER BY created_at DESC"
            if limit:
                query += f" LIMIT {limit}"

            async with db.execute(query) as cursor:
                async for row in cursor:
                    summaries.append(
                        ShortTermSummary(
                            id=row["id"],
                            created_at=datetime.fromisoformat(row["created_at"]),
                            summary=row["summary"],
                            tokens=row["tokens"] or 0,
                            entry_count=row["entry_count"] or 0,
                        )
                    )

        return summaries

    async def add_short_term_summary(self, summary: ShortTermSummary) -> None:
        """Add a compacted short-term summary."""
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO short_term_summaries
                (id, created_at, summary, tokens, entry_count)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    summary.id,
                    summary.created_at.isoformat(),
                    summary.summary,
                    summary.tokens,
                    summary.entry_count,
                ),
            )
            await db.commit()

    async def clear_short_term_entries(self) -> None:
        """Clear all short-term entries (after compaction)."""
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM short_term_entries")
            await db.commit()

    async def get_short_term_content_for_compaction(self) -> str:
        """Get short-term content formatted for compaction."""
        parts = []

        entries = await self.get_short_term_entries()
        if entries:
            parts.append("Recent interactions to summarize:")
            for entry in reversed(entries):
                parts.append(
                    f"\n[{entry.timestamp.isoformat()}]\n"
                    f"Goal: {entry.goal}\n"
                    f"Workflow: {entry.workflow_used}\n"
                    f"Result: {entry.result_summary}"
                )

        return "\n".join(parts)

    # ==================== Long-Term Memory ====================

    async def get_long_term_tokens(self) -> int:
        """Get total tokens in long-term themes."""
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COALESCE(SUM(tokens), 0) FROM long_term_themes"
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def needs_long_term_compaction(self) -> bool:
        """Check if long-term memory needs compaction."""
        # Long-term compaction happens when we have accumulated enough
        # short-term summaries to extract themes
        summary_tokens = await self.get_short_term_summary_tokens()
        theme_tokens = await self.get_long_term_tokens()
        total = summary_tokens + theme_tokens
        threshold = int(self.long_term_max_tokens * self.compact_threshold)
        return total >= threshold

    async def get_long_term_themes(self, limit: int | None = None) -> list[LongTermTheme]:
        """Get long-term themes, most recent first."""
        await self._ensure_initialized()

        themes = []
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = "SELECT * FROM long_term_themes ORDER BY created_at DESC"
            if limit:
                query += f" LIMIT {limit}"

            async with db.execute(query) as cursor:
                async for row in cursor:
                    refs = json.loads(row["short_term_refs"]) if row["short_term_refs"] else []
                    themes.append(
                        LongTermTheme(
                            id=row["id"],
                            created_at=datetime.fromisoformat(row["created_at"]),
                            theme=row["theme"],
                            tokens=row["tokens"] or 0,
                            short_term_refs=refs,
                        )
                    )

        return themes

    async def add_long_term_theme(self, theme: LongTermTheme) -> None:
        """Add a long-term theme."""
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO long_term_themes
                (id, created_at, theme, tokens, short_term_refs)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    theme.id,
                    theme.created_at.isoformat(),
                    theme.theme,
                    theme.tokens,
                    json.dumps(theme.short_term_refs),
                ),
            )
            await db.commit()

    async def get_short_term_summary_by_id(self, summary_id: str) -> ShortTermSummary | None:
        """Get a specific short-term summary by ID."""
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM short_term_summaries WHERE id = ?", (summary_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return ShortTermSummary(
                        id=row["id"],
                        created_at=datetime.fromisoformat(row["created_at"]),
                        summary=row["summary"],
                        tokens=row["tokens"] or 0,
                        entry_count=row["entry_count"] or 0,
                    )
        return None

    async def clear_short_term_summaries(self, keep_ids: list[str] | None = None) -> None:
        """Clear short-term summaries, optionally keeping some."""
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            if keep_ids:
                placeholders = ",".join("?" * len(keep_ids))
                await db.execute(
                    f"DELETE FROM short_term_summaries WHERE id NOT IN ({placeholders})",
                    keep_ids,
                )
            else:
                await db.execute("DELETE FROM short_term_summaries")
            await db.commit()

    async def get_long_term_content_for_compaction(self) -> str:
        """Get long-term content formatted for compaction."""
        parts = []

        # Include existing themes
        themes = await self.get_long_term_themes()
        if themes:
            parts.append("Existing themes (update or consolidate as needed):")
            for theme in themes:
                parts.append(f"\n[Theme from {theme.created_at.date()}]\n{theme.theme}")

        # Include short-term summaries to extract themes from
        summaries = await self.get_short_term_summaries()
        if summaries:
            parts.append("\n\nRecent detailed summaries to extract themes from:")
            for s in summaries:
                parts.append(f"\n[Summary {s.id} from {s.created_at.date()}]\n{s.summary}")

        return "\n".join(parts)

    # ==================== Combined Context ====================

    async def get_context_for_llm(self) -> str:
        """
        Get memory context formatted for LLM.

        Returns long-term themes + recent short-term summaries + very recent entries.
        """
        parts = []

        # Long-term themes (high-level patterns)
        themes = await self.get_long_term_themes(limit=5)
        if themes:
            parts.append("Long-term context (themes and patterns):")
            for theme in themes:
                parts.append(f"  {theme.theme[:200]}...")

        # Short-term summaries (recent detail summaries)
        summaries = await self.get_short_term_summaries(limit=3)
        if summaries:
            parts.append("\nRecent context (summarized):")
            for s in summaries:
                preview = s.summary[:300] + "..." if len(s.summary) > 300 else s.summary
                parts.append(f"  {preview}")

        # Very recent entries (not yet summarized)
        entries = await self.get_short_term_entries(limit=10)
        if entries:
            parts.append("\nRecent interactions:")
            for entry in reversed(entries):
                parts.append(
                    f"  [{entry.timestamp.strftime('%H:%M')}] "
                    f"Goal: {entry.goal[:50]}... -> {entry.workflow_used}"
                )

        return "\n".join(parts) if parts else "No previous context."

    async def get_details_for_theme(self, theme: LongTermTheme) -> str:
        """Get detailed information from short-term summaries referenced by a theme."""
        details = []
        for ref_id in theme.short_term_refs:
            summary = await self.get_short_term_summary_by_id(ref_id)
            if summary:
                details.append(summary.summary)
        return "\n\n".join(details) if details else "No detailed summaries available."

    # ==================== Statistics ====================

    async def get_stats(self) -> dict[str, Any]:
        """Get memory statistics."""
        await self._ensure_initialized()

        short_entries = await self.get_short_term_tokens()
        short_summaries = await self.get_short_term_summary_tokens()
        long_themes = await self.get_long_term_tokens()

        entries = await self.get_short_term_entries()
        summaries = await self.get_short_term_summaries()
        themes = await self.get_long_term_themes()

        return {
            "short_term": {
                "entry_tokens": short_entries,
                "summary_tokens": short_summaries,
                "max_tokens": self.short_term_max_tokens,
                "entry_count": len(entries),
                "summary_count": len(summaries),
            },
            "long_term": {
                "theme_tokens": long_themes,
                "max_tokens": self.long_term_max_tokens,
                "theme_count": len(themes),
            },
        }


def estimate_tokens(text: str) -> int:
    """Rough estimate of tokens in text (chars / 4)."""
    return len(text) // 4
