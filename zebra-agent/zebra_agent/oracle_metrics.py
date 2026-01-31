"""Oracle-based performance metrics tracking for workflows."""

import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import oracledb

logger = logging.getLogger(__name__)


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
            started_at=datetime.now(timezone.utc),
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


class OracleMetricsStore:
    """Oracle-backed store for workflow performance metrics."""

    def __init__(
        self,
        user: str | None = None,
        password: str | None = None,
        dsn: str | None = None,
        wallet_location: str | None = None,
        wallet_password: str | None = None,
        min_pool_size: int = 2,
        max_pool_size: int = 10,
    ):
        self.user = user or os.environ.get("ORACLE_USERNAME")
        self.password = password or os.environ.get("ORACLE_PASSWORD")
        self.dsn = dsn or os.environ.get("ORACLE_DSN")
        self.wallet_location = wallet_location or os.environ.get("ORACLE_WALLET_LOCATION")
        self.wallet_password = wallet_password or os.environ.get("ORACLE_WALLET_PASSWORD")
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

    async def _ensure_pool(self) -> oracledb.AsyncConnectionPool:
        """Ensure connection pool is initialized."""
        if self._pool is None:
            await self.initialize()
        return self._pool

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

        async with self._pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # Create workflow_runs table
                await cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS workflow_runs (
                        id VARCHAR2(255) PRIMARY KEY,
                        workflow_name VARCHAR2(255) NOT NULL,
                        goal VARCHAR2(4000) NOT NULL,
                        started_at TIMESTAMP WITH TIME ZONE NOT NULL,
                        completed_at TIMESTAMP WITH TIME ZONE,
                        success NUMBER(1) DEFAULT 0 NOT NULL,
                        user_rating NUMBER CHECK (user_rating >= 1 AND user_rating <= 5),
                        tokens_used NUMBER DEFAULT 0,
                        error VARCHAR2(4000),
                        output VARCHAR2(4000)
                    )
                    """
                )

                # Create indexes
                try:
                    await cursor.execute(
                        "CREATE INDEX idx_runs_workflow ON workflow_runs(workflow_name)"
                    )
                except oracledb.DatabaseError as e:
                    if "ORA-00955" not in str(e):
                        raise

                try:
                    await cursor.execute(
                        "CREATE INDEX idx_runs_started ON workflow_runs(started_at DESC)"
                    )
                except oracledb.DatabaseError as e:
                    if "ORA-00955" not in str(e):
                        raise

            await conn.commit()

        self._initialized = True

    async def _ensure_initialized(self) -> None:
        """Backwards compatibility wrapper for initialize()."""
        await self.initialize()

    async def close(self) -> None:
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def record_run(self, run: WorkflowRun) -> None:
        """Record a workflow run."""
        await self.initialize()
        pool = await self._ensure_pool()

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    MERGE INTO workflow_runs r
                    USING (SELECT :1 AS id, :2 AS workflow_name, :3 AS goal,
                                  :4 AS started_at, :5 AS completed_at, :6 AS success,
                                  :7 AS user_rating, :8 AS tokens_used, :9 AS error, :10 AS output FROM dual) s
                    ON (r.id = s.id)
                    WHEN MATCHED THEN
                        UPDATE SET workflow_name = s.workflow_name, goal = s.goal,
                                   started_at = s.started_at, completed_at = s.completed_at,
                                   success = s.success, user_rating = s.user_rating,
                                   tokens_used = s.tokens_used, error = s.error, output = s.output
                    WHEN NOT MATCHED THEN
                        INSERT (id, workflow_name, goal, started_at, completed_at,
                                success, user_rating, tokens_used, error, output)
                        VALUES (s.id, s.workflow_name, s.goal, s.started_at, s.completed_at,
                                s.success, s.user_rating, s.tokens_used, s.error, s.output)
                    """,
                    [
                        run.id,
                        run.workflow_name,
                        run.goal,
                        run.started_at,
                        run.completed_at,
                        1 if run.success else 0,
                        run.user_rating,
                        run.tokens_used,
                        run.error,
                        str(run.output) if run.output else None,
                    ],
                )
            await conn.commit()

    async def update_rating(self, run_id: str, rating: int) -> None:
        """Update the user rating for a run."""
        if not 1 <= rating <= 5:
            raise ValueError("Rating must be between 1 and 5")

        await self.initialize()
        pool = await self._ensure_pool()

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "UPDATE workflow_runs SET user_rating = :1 WHERE id = :2",
                    [rating, run_id],
                )
            await conn.commit()

    async def get_run(self, run_id: str) -> WorkflowRun | None:
        """Get a specific run by ID."""
        await self.initialize()
        pool = await self._ensure_pool()

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT id, workflow_name, goal, started_at, completed_at,
                           success, user_rating, tokens_used, error, output
                    FROM workflow_runs WHERE id = :1
                    """,
                    [run_id],
                )
                row = await cursor.fetchone()
                if row:
                    return self._row_to_run(row)
                return None

    async def get_stats(self, workflow_name: str) -> WorkflowStats:
        """Get aggregated stats for a workflow."""
        await self.initialize()
        pool = await self._ensure_pool()

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT
                        COUNT(*) as total_runs,
                        SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful_runs,
                        AVG(user_rating) as avg_rating,
                        MAX(started_at) as last_used
                    FROM workflow_runs
                    WHERE workflow_name = :1
                    """,
                    [workflow_name],
                )
                row = await cursor.fetchone()

        if row and row[0] > 0:
            return WorkflowStats(
                workflow_name=workflow_name,
                total_runs=row[0],
                successful_runs=row[1] or 0,
                avg_rating=float(row[2]) if row[2] else None,
                last_used=row[3],
            )

        return WorkflowStats(workflow_name=workflow_name)

    async def get_all_stats(self) -> list[WorkflowStats]:
        """Get stats for all workflows."""
        await self.initialize()
        pool = await self._ensure_pool()

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT
                        workflow_name,
                        COUNT(*) as total_runs,
                        SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful_runs,
                        AVG(user_rating) as avg_rating,
                        MAX(started_at) as last_used
                    FROM workflow_runs
                    GROUP BY workflow_name
                    ORDER BY total_runs DESC
                    """
                )
                rows = await cursor.fetchall()

        stats = []
        for row in rows:
            stats.append(
                WorkflowStats(
                    workflow_name=row[0],
                    total_runs=row[1],
                    successful_runs=row[2] or 0,
                    avg_rating=float(row[3]) if row[3] else None,
                    last_used=row[4],
                )
            )

        return stats

    async def get_recent_runs(self, limit: int = 10) -> list[WorkflowRun]:
        """Get the most recent workflow runs."""
        await self.initialize()
        pool = await self._ensure_pool()

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT id, workflow_name, goal, started_at, completed_at,
                           success, user_rating, tokens_used, error, output
                    FROM workflow_runs
                    ORDER BY started_at DESC
                    FETCH FIRST :1 ROWS ONLY
                    """,
                    [limit],
                )
                rows = await cursor.fetchall()

        return [self._row_to_run(row) for row in rows]

    async def get_runs_for_workflow(self, workflow_name: str, limit: int = 10) -> list[WorkflowRun]:
        """Get recent runs for a specific workflow."""
        await self.initialize()
        pool = await self._ensure_pool()

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT id, workflow_name, goal, started_at, completed_at,
                           success, user_rating, tokens_used, error, output
                    FROM workflow_runs
                    WHERE workflow_name = :1
                    ORDER BY started_at DESC
                    FETCH FIRST :2 ROWS ONLY
                    """,
                    [workflow_name, limit],
                )
                rows = await cursor.fetchall()

        return [self._row_to_run(row) for row in rows]

    def _row_to_run(self, row: tuple) -> WorkflowRun:
        """Convert a database row to a WorkflowRun."""
        return WorkflowRun(
            id=row[0],
            workflow_name=row[1],
            goal=row[2],
            started_at=row[3],
            completed_at=row[4],
            success=bool(row[5]),
            user_rating=row[6],
            tokens_used=row[7] or 0,
            error=row[8],
            output=row[9],
        )
