"""Oracle-based memory for agent conversations with short-term and long-term storage."""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import oracledb

logger = logging.getLogger(__name__)


def _read_clob(value: Any) -> str | None:
    """Safely read a CLOB value from Oracle.

    Handles cases where the value might be:
    - Already a string
    - A file-like object with .read()
    - A dict (JSON data)
    - None
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return json.dumps(value)
    if hasattr(value, "read"):
        return value.read()
    return str(value)


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


class OracleAgentMemory:
    """
    Agent memory with short-term and long-term storage backed by Oracle.

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
        user: str | None = None,
        password: str | None = None,
        dsn: str | None = None,
        wallet_location: str | None = None,
        wallet_password: str | None = None,
        short_term_max_tokens: int = 20000,
        long_term_max_tokens: int = 30000,
        compact_threshold: float = 0.9,
        min_pool_size: int = 2,
        max_pool_size: int = 10,
    ):
        self.user = user or os.environ.get("ORACLE_USERNAME")
        self.password = password or os.environ.get("ORACLE_PASSWORD")
        self.dsn = dsn or os.environ.get("ORACLE_DSN")
        self.wallet_location = wallet_location or os.environ.get("ORACLE_WALLET_LOCATION")
        self.wallet_password = wallet_password or os.environ.get("ORACLE_WALLET_PASSWORD")
        self.short_term_max_tokens = short_term_max_tokens
        self.long_term_max_tokens = long_term_max_tokens
        self.compact_threshold = compact_threshold
        self.min_pool_size = min_pool_size
        self.max_pool_size = max_pool_size
        self._pool: oracledb.AsyncConnectionPool | None = None
        self._initialized = False

        if not self.user:
            raise ValueError("Oracle user required (set ORACLE_USERNAME env var)")
        if not self.password:
            raise ValueError("Oracle password required (set ORACLE_PASSWORD env var)")
        if not self.dsn:
            raise ValueError("Oracle DSN required (set ORACLE_DSN env var)")

    async def initialize(self) -> None:
        """Initialize database schema."""
        if self._initialized:
            return

        # Create connection pool
        pool_params: dict[str, Any] = {
            "user": self.user,
            "password": self.password,
            "dsn": self.dsn,
            "min": self.min_pool_size,
            "max": self.max_pool_size,
        }

        if self.wallet_location:
            pool_params["config_dir"] = self.wallet_location
            pool_params["wallet_location"] = self.wallet_location
            if self.wallet_password:
                pool_params["wallet_password"] = self.wallet_password

        self._pool = oracledb.create_pool_async(**pool_params)

        # Create tables
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # Short-term: individual interaction entries
                await cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS short_term_entries (
                        id VARCHAR2(255) PRIMARY KEY,
                        timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
                        goal VARCHAR2(4000) NOT NULL,
                        workflow_used VARCHAR2(255),
                        result_summary VARCHAR2(4000),
                        tokens NUMBER DEFAULT 0
                    )
                    """
                )

                # Short-term: compacted summaries
                await cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS short_term_summaries (
                        id VARCHAR2(255) PRIMARY KEY,
                        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                        summary CLOB NOT NULL,
                        tokens NUMBER DEFAULT 0,
                        entry_count NUMBER DEFAULT 0
                    )
                    """
                )

                # Long-term: thematic summaries
                await cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS long_term_themes (
                        id VARCHAR2(255) PRIMARY KEY,
                        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                        theme CLOB NOT NULL,
                        tokens NUMBER DEFAULT 0,
                        short_term_refs CLOB CHECK (short_term_refs IS JSON)
                    )
                    """
                )

                # State tracking
                await cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS memory_state (
                        key VARCHAR2(255) PRIMARY KEY,
                        value VARCHAR2(4000)
                    )
                    """
                )

                # Create indexes
                try:
                    await cursor.execute(
                        "CREATE INDEX idx_ste_timestamp ON short_term_entries(timestamp DESC)"
                    )
                except oracledb.DatabaseError as e:
                    if "ORA-00955" not in str(e):
                        raise

                try:
                    await cursor.execute(
                        "CREATE INDEX idx_sts_created ON short_term_summaries(created_at DESC)"
                    )
                except oracledb.DatabaseError as e:
                    if "ORA-00955" not in str(e):
                        raise

                try:
                    await cursor.execute(
                        "CREATE INDEX idx_lt_created ON long_term_themes(created_at DESC)"
                    )
                except oracledb.DatabaseError as e:
                    if "ORA-00955" not in str(e):
                        raise

            await conn.commit()

        self._initialized = True

    async def _ensure_pool(self) -> oracledb.AsyncConnectionPool:
        """Ensure connection pool is initialized."""
        if self._pool is None:
            await self.initialize()
        return self._pool

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

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    MERGE INTO short_term_entries t
                    USING (SELECT :1 AS id, :2 AS timestamp, :3 AS goal,
                                  :4 AS workflow_used, :5 AS result_summary, :6 AS tokens FROM dual) s
                    ON (t.id = s.id)
                    WHEN MATCHED THEN
                        UPDATE SET timestamp = s.timestamp, goal = s.goal,
                                   workflow_used = s.workflow_used,
                                   result_summary = s.result_summary, tokens = s.tokens
                    WHEN NOT MATCHED THEN
                        INSERT (id, timestamp, goal, workflow_used, result_summary, tokens)
                        VALUES (s.id, s.timestamp, s.goal, s.workflow_used, s.result_summary, s.tokens)
                    """,
                    [
                        entry.id,
                        entry.timestamp,
                        entry.goal,
                        entry.workflow_used,
                        entry.result_summary,
                        entry.tokens,
                    ],
                )
            await conn.commit()

    async def get_short_term_entries(self, limit: int | None = None) -> list[MemoryEntry]:
        """Get short-term entries, most recent first."""
        await self.initialize()
        pool = await self._ensure_pool()

        query = "SELECT id, timestamp, goal, workflow_used, result_summary, tokens FROM short_term_entries ORDER BY timestamp DESC"
        params: list[Any] = []
        if limit:
            query += " FETCH FIRST :1 ROWS ONLY"
            params.append(limit)

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, params)
                rows = await cursor.fetchall()

        return [
            MemoryEntry(
                id=row[0],
                timestamp=row[1],
                goal=row[2],
                workflow_used=row[3] or "",
                result_summary=row[4] or "",
                tokens=row[5] or 0,
            )
            for row in rows
        ]

    async def get_short_term_tokens(self) -> int:
        """Get total tokens in short-term entries."""
        await self.initialize()
        pool = await self._ensure_pool()

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT COALESCE(SUM(tokens), 0) FROM short_term_entries")
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def get_short_term_summary_tokens(self) -> int:
        """Get total tokens in short-term summaries."""
        await self.initialize()
        pool = await self._ensure_pool()

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT COALESCE(SUM(tokens), 0) FROM short_term_summaries")
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def needs_short_term_compaction(self) -> bool:
        """Check if short-term memory needs compaction."""
        total = await self.get_short_term_tokens()
        threshold = int(self.short_term_max_tokens * self.compact_threshold)
        return total >= threshold

    async def get_short_term_summaries(self, limit: int | None = None) -> list[ShortTermSummary]:
        """Get short-term summaries, most recent first."""
        await self.initialize()
        pool = await self._ensure_pool()

        query = "SELECT id, created_at, summary, tokens, entry_count FROM short_term_summaries ORDER BY created_at DESC"
        params: list[Any] = []
        if limit:
            query += " FETCH FIRST :1 ROWS ONLY"
            params.append(limit)

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, params)
                rows = await cursor.fetchall()

        return [
            ShortTermSummary(
                id=row[0],
                created_at=row[1],
                summary=_read_clob(row[2]) or "",
                tokens=row[3] or 0,
                entry_count=row[4] or 0,
            )
            for row in rows
        ]

    async def add_short_term_summary(self, summary: ShortTermSummary) -> None:
        """Add a compacted short-term summary."""
        await self.initialize()
        pool = await self._ensure_pool()

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    INSERT INTO short_term_summaries (id, created_at, summary, tokens, entry_count)
                    VALUES (:1, :2, :3, :4, :5)
                    """,
                    [
                        summary.id,
                        summary.created_at,
                        summary.summary,
                        summary.tokens,
                        summary.entry_count,
                    ],
                )
            await conn.commit()

    async def clear_short_term_entries(self) -> None:
        """Clear all short-term entries (after compaction)."""
        await self.initialize()
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("DELETE FROM short_term_entries")
            await conn.commit()

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

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT COALESCE(SUM(tokens), 0) FROM long_term_themes")
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def needs_long_term_compaction(self) -> bool:
        """Check if long-term memory needs compaction."""
        summary_tokens = await self.get_short_term_summary_tokens()
        theme_tokens = await self.get_long_term_tokens()
        total = summary_tokens + theme_tokens
        threshold = int(self.long_term_max_tokens * self.compact_threshold)
        return total >= threshold

    async def get_long_term_themes(self, limit: int | None = None) -> list[LongTermTheme]:
        """Get long-term themes, most recent first."""
        await self.initialize()
        pool = await self._ensure_pool()

        query = "SELECT id, created_at, theme, tokens, short_term_refs FROM long_term_themes ORDER BY created_at DESC"
        params: list[Any] = []
        if limit:
            query += " FETCH FIRST :1 ROWS ONLY"
            params.append(limit)

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, params)
                rows = await cursor.fetchall()

        themes = []
        for row in rows:
            refs_data = _read_clob(row[4])
            refs = json.loads(refs_data) if refs_data else []
            if isinstance(refs, str):
                refs = json.loads(refs)

            themes.append(
                LongTermTheme(
                    id=row[0],
                    created_at=row[1],
                    theme=_read_clob(row[2]) or "",
                    tokens=row[3] or 0,
                    short_term_refs=refs,
                )
            )

        return themes

    async def add_long_term_theme(self, theme: LongTermTheme) -> None:
        """Add a long-term theme."""
        await self.initialize()
        pool = await self._ensure_pool()

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    INSERT INTO long_term_themes (id, created_at, theme, tokens, short_term_refs)
                    VALUES (:1, :2, :3, :4, :5)
                    """,
                    [
                        theme.id,
                        theme.created_at,
                        theme.theme,
                        theme.tokens,
                        json.dumps(theme.short_term_refs),
                    ],
                )
            await conn.commit()

    async def get_short_term_summary_by_id(self, summary_id: str) -> ShortTermSummary | None:
        """Get a specific short-term summary by ID."""
        await self.initialize()
        pool = await self._ensure_pool()

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "SELECT id, created_at, summary, tokens, entry_count FROM short_term_summaries WHERE id = :1",
                    [summary_id],
                )
                row = await cursor.fetchone()
                if row:
                    return ShortTermSummary(
                        id=row[0],
                        created_at=row[1],
                        summary=_read_clob(row[2]) or "",
                        tokens=row[3] or 0,
                        entry_count=row[4] or 0,
                    )
                return None

    async def clear_short_term_summaries(self, keep_ids: list[str] | None = None) -> None:
        """Clear short-term summaries, optionally keeping some."""
        await self.initialize()
        pool = await self._ensure_pool()

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                if keep_ids:
                    # Delete where id NOT IN (keep_ids)
                    placeholders = ", ".join([f":{i + 1}" for i in range(len(keep_ids))])
                    await cursor.execute(
                        f"DELETE FROM short_term_summaries WHERE id NOT IN ({placeholders})",
                        keep_ids,
                    )
                else:
                    await cursor.execute("DELETE FROM short_term_summaries")
            await conn.commit()

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
