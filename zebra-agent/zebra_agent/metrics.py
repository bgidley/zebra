"""Performance metrics tracking for workflows."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite


@dataclass
class WorkflowRun:
    """Record of a single workflow execution."""

    id: str
    workflow_name: str
    goal: str
    started_at: datetime
    completed_at: datetime | None = None
    success: bool = False
    user_rating: int | None = None  # 1-5
    tokens_used: int = 0
    error: str | None = None
    output: Any = None

    @classmethod
    def create(cls, workflow_name: str, goal: str) -> "WorkflowRun":
        """Create a new workflow run."""
        return cls(
            id=str(uuid.uuid4()),
            workflow_name=workflow_name,
            goal=goal,
            started_at=datetime.now(),
        )


@dataclass
class WorkflowStats:
    """Aggregated statistics for a workflow."""

    workflow_name: str
    total_runs: int = 0
    successful_runs: int = 0
    avg_rating: float | None = None
    last_used: datetime | None = None

    @property
    def success_rate(self) -> float:
        """Calculate success rate as a fraction."""
        if self.total_runs == 0:
            return 0.0
        return self.successful_runs / self.total_runs


class MetricsStore:
    """SQLite-backed store for workflow performance metrics."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path).expanduser()
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        """Ensure database tables exist."""
        if self._initialized:
            return

        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS workflow_runs (
                    id TEXT PRIMARY KEY,
                    workflow_name TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    success INTEGER NOT NULL DEFAULT 0,
                    user_rating INTEGER,
                    tokens_used INTEGER DEFAULT 0,
                    error TEXT,
                    output TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_runs_workflow
                ON workflow_runs(workflow_name);

                CREATE INDEX IF NOT EXISTS idx_runs_started
                ON workflow_runs(started_at);
                """
            )
            await db.commit()

        self._initialized = True

    async def record_run(self, run: WorkflowRun) -> None:
        """Record a workflow run."""
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO workflow_runs
                (id, workflow_name, goal, started_at, completed_at,
                 success, user_rating, tokens_used, error, output)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.id,
                    run.workflow_name,
                    run.goal,
                    run.started_at.isoformat(),
                    run.completed_at.isoformat() if run.completed_at else None,
                    1 if run.success else 0,
                    run.user_rating,
                    run.tokens_used,
                    run.error,
                    str(run.output) if run.output else None,
                ),
            )
            await db.commit()

    async def update_rating(self, run_id: str, rating: int) -> None:
        """Update the user rating for a run."""
        await self._ensure_initialized()

        if not 1 <= rating <= 5:
            raise ValueError("Rating must be between 1 and 5")

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE workflow_runs SET user_rating = ? WHERE id = ?",
                (rating, run_id),
            )
            await db.commit()

    async def get_run(self, run_id: str) -> WorkflowRun | None:
        """Get a specific run by ID."""
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM workflow_runs WHERE id = ?", (run_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return self._row_to_run(row)
        return None

    async def get_stats(self, workflow_name: str) -> WorkflowStats:
        """Get aggregated stats for a workflow."""
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # Get counts
            async with db.execute(
                """
                SELECT
                    COUNT(*) as total_runs,
                    SUM(success) as successful_runs,
                    AVG(user_rating) as avg_rating,
                    MAX(started_at) as last_used
                FROM workflow_runs
                WHERE workflow_name = ?
                """,
                (workflow_name,),
            ) as cursor:
                row = await cursor.fetchone()

                if row and row["total_runs"] > 0:
                    last_used = None
                    if row["last_used"]:
                        last_used = datetime.fromisoformat(row["last_used"])

                    return WorkflowStats(
                        workflow_name=workflow_name,
                        total_runs=row["total_runs"],
                        successful_runs=row["successful_runs"] or 0,
                        avg_rating=row["avg_rating"],
                        last_used=last_used,
                    )

        return WorkflowStats(workflow_name=workflow_name)

    async def get_all_stats(self) -> list[WorkflowStats]:
        """Get stats for all workflows."""
        await self._ensure_initialized()

        stats = []
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            async with db.execute(
                """
                SELECT
                    workflow_name,
                    COUNT(*) as total_runs,
                    SUM(success) as successful_runs,
                    AVG(user_rating) as avg_rating,
                    MAX(started_at) as last_used
                FROM workflow_runs
                GROUP BY workflow_name
                ORDER BY total_runs DESC
                """
            ) as cursor:
                async for row in cursor:
                    last_used = None
                    if row["last_used"]:
                        last_used = datetime.fromisoformat(row["last_used"])

                    stats.append(
                        WorkflowStats(
                            workflow_name=row["workflow_name"],
                            total_runs=row["total_runs"],
                            successful_runs=row["successful_runs"] or 0,
                            avg_rating=row["avg_rating"],
                            last_used=last_used,
                        )
                    )

        return stats

    async def get_recent_runs(self, limit: int = 10) -> list[WorkflowRun]:
        """Get the most recent workflow runs."""
        await self._ensure_initialized()

        runs = []
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            async with db.execute(
                """
                SELECT * FROM workflow_runs
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (limit,),
            ) as cursor:
                async for row in cursor:
                    runs.append(self._row_to_run(row))

        return runs

    def _row_to_run(self, row: aiosqlite.Row) -> WorkflowRun:
        """Convert a database row to a WorkflowRun."""
        completed_at = None
        if row["completed_at"]:
            completed_at = datetime.fromisoformat(row["completed_at"])

        return WorkflowRun(
            id=row["id"],
            workflow_name=row["workflow_name"],
            goal=row["goal"],
            started_at=datetime.fromisoformat(row["started_at"]),
            completed_at=completed_at,
            success=bool(row["success"]),
            user_rating=row["user_rating"],
            tokens_used=row["tokens_used"] or 0,
            error=row["error"],
            output=row["output"],
        )
