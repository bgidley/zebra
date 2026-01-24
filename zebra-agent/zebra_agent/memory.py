"""Local memory for agent conversations with short-term and long-term storage."""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import asyncpg


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
    Agent memory with short-term and long-term storage backed by PostgreSQL.

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
        host: str = "localhost",
        port: int = 5432,
        database: str = "opc",
        user: str = "opc",
        password: str | None = None,
        short_term_max_tokens: int = 20000,
        long_term_max_tokens: int = 30000,
        compact_threshold: float = 0.9,
        min_pool_size: int = 2,
        max_pool_size: int = 10,
    ):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.short_term_max_tokens = short_term_max_tokens
        self.long_term_max_tokens = long_term_max_tokens
        self.compact_threshold = compact_threshold
        self.min_pool_size = min_pool_size
        self.max_pool_size = max_pool_size
        self._pool: asyncpg.Pool | None = None
        self._initialized = False

    async def _ensure_pool(self) -> asyncpg.Pool:
        """Ensure connection pool is initialized."""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                min_size=self.min_pool_size,
                max_size=self.max_pool_size,
            )
        return self._pool

    async def initialize(self) -> None:
        """Initialize database schema."""
        if self._initialized:
            return

        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                -- Short-term: individual interaction entries
                CREATE TABLE IF NOT EXISTS short_term_entries (
                    id TEXT PRIMARY KEY,
                    timestamp TIMESTAMPTZ NOT NULL,
                    goal TEXT NOT NULL,
                    workflow_used TEXT,
                    result_summary TEXT,
                    tokens INTEGER DEFAULT 0
                );

                -- Short-term: compacted summaries (detail-focused)
                CREATE TABLE IF NOT EXISTS short_term_summaries (
                    id TEXT PRIMARY KEY,
                    created_at TIMESTAMPTZ NOT NULL,
                    summary TEXT NOT NULL,
                    tokens INTEGER DEFAULT 0,
                    entry_count INTEGER DEFAULT 0
                );

                -- Long-term: thematic summaries
                CREATE TABLE IF NOT EXISTS long_term_themes (
                    id TEXT PRIMARY KEY,
                    created_at TIMESTAMPTZ NOT NULL,
                    theme TEXT NOT NULL,
                    tokens INTEGER DEFAULT 0,
                    short_term_refs JSONB DEFAULT '[]'::jsonb
                );

                -- State tracking
                CREATE TABLE IF NOT EXISTS memory_state (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_short_term_timestamp
                ON short_term_entries(timestamp DESC);

                CREATE INDEX IF NOT EXISTS idx_short_term_summary_created
                ON short_term_summaries(created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_long_term_created
                ON long_term_themes(created_at DESC);
                """
            )
        self._initialized = True

    async def _ensure_initialized(self) -> None:
        """Backwards compatibility wrapper for initialize()."""
        await self.initialize()

    async def close(self) -> None:
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    # ==================== Short-Term Memory ====================

    async def add_entry(self, entry: MemoryEntry) -> None:
        """Add an entry to short-term memory."""
        await self.initialize()
        pool = await self._ensure_pool()

        await pool.execute(
            """
            INSERT INTO short_term_entries
            (id, timestamp, goal, workflow_used, result_summary, tokens)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (id) DO UPDATE SET
                timestamp = EXCLUDED.timestamp,
                goal = EXCLUDED.goal,
                workflow_used = EXCLUDED.workflow_used,
                result_summary = EXCLUDED.result_summary,
                tokens = EXCLUDED.tokens
            """,
            entry.id,
            entry.timestamp,
            entry.goal,
            entry.workflow_used,
            entry.result_summary,
            entry.tokens,
        )

    async def get_short_term_entries(self, limit: int | None = None) -> list[MemoryEntry]:
        """Get short-term entries, most recent first."""
        await self.initialize()
        pool = await self._ensure_pool()

        query = "SELECT * FROM short_term_entries ORDER BY timestamp DESC"
        if limit:
            query += f" LIMIT {limit}"

        rows = await pool.fetch(query)

        return [
            MemoryEntry(
                id=row["id"],
                timestamp=row["timestamp"],
                goal=row["goal"],
                workflow_used=row["workflow_used"] or "",
                result_summary=row["result_summary"] or "",
                tokens=row["tokens"] or 0,
            )
            for row in rows
        ]

    async def get_short_term_tokens(self) -> int:
        """Get total tokens in short-term entries."""
        await self.initialize()
        pool = await self._ensure_pool()

        val = await pool.fetchval("SELECT COALESCE(SUM(tokens), 0) FROM short_term_entries")
        return val or 0

    async def get_short_term_summary_tokens(self) -> int:
        """Get total tokens in short-term summaries."""
        await self.initialize()
        pool = await self._ensure_pool()

        val = await pool.fetchval("SELECT COALESCE(SUM(tokens), 0) FROM short_term_summaries")
        return val or 0

    async def needs_short_term_compaction(self) -> bool:
        """Check if short-term memory needs compaction."""
        total = await self.get_short_term_tokens()
        threshold = int(self.short_term_max_tokens * self.compact_threshold)
        return total >= threshold

    async def get_short_term_summaries(self, limit: int | None = None) -> list[ShortTermSummary]:
        """Get short-term summaries, most recent first."""
        await self.initialize()
        pool = await self._ensure_pool()

        query = "SELECT * FROM short_term_summaries ORDER BY created_at DESC"
        if limit:
            query += f" LIMIT {limit}"

        rows = await pool.fetch(query)

        return [
            ShortTermSummary(
                id=row["id"],
                created_at=row["created_at"],
                summary=row["summary"],
                tokens=row["tokens"] or 0,
                entry_count=row["entry_count"] or 0,
            )
            for row in rows
        ]

    async def add_short_term_summary(self, summary: ShortTermSummary) -> None:
        """Add a compacted short-term summary."""
        await self.initialize()
        pool = await self._ensure_pool()

        await pool.execute(
            """
            INSERT INTO short_term_summaries
            (id, created_at, summary, tokens, entry_count)
            VALUES ($1, $2, $3, $4, $5)
            """,
            summary.id,
            summary.created_at,
            summary.summary,
            summary.tokens,
            summary.entry_count,
        )

    async def clear_short_term_entries(self) -> None:
        """Clear all short-term entries (after compaction)."""
        await self.initialize()
        pool = await self._ensure_pool()
        await pool.execute("DELETE FROM short_term_entries")

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
        await self.initialize()
        pool = await self._ensure_pool()

        val = await pool.fetchval("SELECT COALESCE(SUM(tokens), 0) FROM long_term_themes")
        return val or 0

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
        await self.initialize()
        pool = await self._ensure_pool()

        query = "SELECT * FROM long_term_themes ORDER BY created_at DESC"
        if limit:
            query += f" LIMIT {limit}"

        rows = await pool.fetch(query)

        themes = []
        for row in rows:
            # asyncpg automatically decodes JSONB to python dict/list
            refs = row["short_term_refs"] if row["short_term_refs"] else []
            if isinstance(refs, str):
                refs = json.loads(refs)

            themes.append(
                LongTermTheme(
                    id=row["id"],
                    created_at=row["created_at"],
                    theme=row["theme"],
                    tokens=row["tokens"] or 0,
                    short_term_refs=refs,
                )
            )

        return themes

    async def add_long_term_theme(self, theme: LongTermTheme) -> None:
        """Add a long-term theme."""
        await self.initialize()
        pool = await self._ensure_pool()

        await pool.execute(
            """
            INSERT INTO long_term_themes
            (id, created_at, theme, tokens, short_term_refs)
            VALUES ($1, $2, $3, $4, $5)
            """,
            theme.id,
            theme.created_at,
            theme.theme,
            theme.tokens,
            json.dumps(theme.short_term_refs),
        )

    async def get_short_term_summary_by_id(self, summary_id: str) -> ShortTermSummary | None:
        """Get a specific short-term summary by ID."""
        await self.initialize()
        pool = await self._ensure_pool()

        row = await pool.fetchrow("SELECT * FROM short_term_summaries WHERE id = $1", summary_id)
        if row:
            return ShortTermSummary(
                id=row["id"],
                created_at=row["created_at"],
                summary=row["summary"],
                tokens=row["tokens"] or 0,
                entry_count=row["entry_count"] or 0,
            )
        return None

    async def clear_short_term_summaries(self, keep_ids: list[str] | None = None) -> None:
        """Clear short-term summaries, optionally keeping some."""
        await self.initialize()
        pool = await self._ensure_pool()

        if keep_ids:
            # asyncpg handles list parameters with ANY
            await pool.execute(
                "DELETE FROM short_term_summaries WHERE id != ANY($1)",
                keep_ids,
            )
        else:
            await pool.execute("DELETE FROM short_term_summaries")

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
        await self.initialize()

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
