"""Performance metrics tracking for workflows."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import asyncpg


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
            started_at=datetime.now(UTC),
        )


@dataclass
class TaskExecution:
    """Record of a single task execution within a workflow run."""

    id: str
    run_id: str  # Foreign key to WorkflowRun.id
    task_definition_id: str  # Task ID from definition (e.g., "analyze")
    task_name: str  # Human-readable name
    execution_order: int  # Order in execution sequence (1-based)
    state: str  # "complete" | "failed" | "skipped"
    started_at: datetime
    completed_at: datetime | None = None
    output: Any = None  # Task result/output
    error: str | None = None  # Error message if failed

    @classmethod
    def create(
        cls,
        run_id: str,
        task_definition_id: str,
        task_name: str,
        execution_order: int,
    ) -> "TaskExecution":
        """Create a new task execution record."""
        return cls(
            id=str(uuid.uuid4()),
            run_id=run_id,
            task_definition_id=task_definition_id,
            task_name=task_name,
            execution_order=execution_order,
            state="running",
            started_at=datetime.now(UTC),
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
    """PostgreSQL-backed store for workflow performance metrics."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "opc",
        user: str = "opc",
        password: str | None = None,
        min_pool_size: int = 2,
        max_pool_size: int = 10,
    ):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
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
                CREATE TABLE IF NOT EXISTS workflow_runs (
                    id TEXT PRIMARY KEY,
                    workflow_name TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    started_at TIMESTAMPTZ NOT NULL,
                    completed_at TIMESTAMPTZ,
                    success BOOLEAN NOT NULL DEFAULT FALSE,
                    user_rating INTEGER CHECK (user_rating >= 1 AND user_rating <= 5),
                    tokens_used INTEGER DEFAULT 0,
                    error TEXT,
                    output TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_runs_workflow
                ON workflow_runs(workflow_name);

                CREATE INDEX IF NOT EXISTS idx_runs_started
                ON workflow_runs(started_at DESC);

                CREATE TABLE IF NOT EXISTS workflow_task_executions (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
                    task_definition_id TEXT NOT NULL,
                    task_name TEXT NOT NULL,
                    execution_order INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    started_at TIMESTAMPTZ NOT NULL,
                    completed_at TIMESTAMPTZ,
                    output TEXT,
                    error TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_task_exec_run
                ON workflow_task_executions(run_id);

                CREATE INDEX IF NOT EXISTS idx_task_exec_order
                ON workflow_task_executions(run_id, execution_order);
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

    async def record_run(self, run: WorkflowRun) -> None:
        """Record a workflow run."""
        await self.initialize()
        pool = await self._ensure_pool()

        await pool.execute(
            """
            INSERT INTO workflow_runs
            (id, workflow_name, goal, started_at, completed_at,
             success, user_rating, tokens_used, error, output)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (id) DO UPDATE SET
                workflow_name = EXCLUDED.workflow_name,
                goal = EXCLUDED.goal,
                started_at = EXCLUDED.started_at,
                completed_at = EXCLUDED.completed_at,
                success = EXCLUDED.success,
                user_rating = EXCLUDED.user_rating,
                tokens_used = EXCLUDED.tokens_used,
                error = EXCLUDED.error,
                output = EXCLUDED.output
            """,
            run.id,
            run.workflow_name,
            run.goal,
            run.started_at,
            run.completed_at,
            run.success,
            run.user_rating,
            run.tokens_used,
            run.error,
            str(run.output) if run.output else None,
        )

    async def update_rating(self, run_id: str, rating: int) -> None:
        """Update the user rating for a run."""
        if not 1 <= rating <= 5:
            raise ValueError("Rating must be between 1 and 5")

        await self.initialize()
        pool = await self._ensure_pool()

        await pool.execute(
            "UPDATE workflow_runs SET user_rating = $1 WHERE id = $2",
            rating,
            run_id,
        )

    async def get_run(self, run_id: str) -> WorkflowRun | None:
        """Get a specific run by ID."""
        await self.initialize()
        pool = await self._ensure_pool()

        row = await pool.fetchrow("SELECT * FROM workflow_runs WHERE id = $1", run_id)
        if row:
            return self._row_to_run(row)
        return None

    async def get_stats(self, workflow_name: str) -> WorkflowStats:
        """Get aggregated stats for a workflow."""
        await self.initialize()
        pool = await self._ensure_pool()

        row = await pool.fetchrow(
            """
            SELECT
                COUNT(*) as total_runs,
                SUM(CASE WHEN success THEN 1 ELSE 0 END) as successful_runs,
                AVG(user_rating) as avg_rating,
                MAX(started_at) as last_used
            FROM workflow_runs
            WHERE workflow_name = $1
            """,
            workflow_name,
        )

        if row and row["total_runs"] > 0:
            return WorkflowStats(
                workflow_name=workflow_name,
                total_runs=row["total_runs"],
                successful_runs=row["successful_runs"] or 0,
                avg_rating=float(row["avg_rating"]) if row["avg_rating"] else None,
                last_used=row["last_used"],
            )

        return WorkflowStats(workflow_name=workflow_name)

    async def get_all_stats(self) -> list[WorkflowStats]:
        """Get stats for all workflows."""
        await self.initialize()
        pool = await self._ensure_pool()

        rows = await pool.fetch(
            """
            SELECT
                workflow_name,
                COUNT(*) as total_runs,
                SUM(CASE WHEN success THEN 1 ELSE 0 END) as successful_runs,
                AVG(user_rating) as avg_rating,
                MAX(started_at) as last_used
            FROM workflow_runs
            GROUP BY workflow_name
            ORDER BY total_runs DESC
            """
        )

        stats = []
        for row in rows:
            stats.append(
                WorkflowStats(
                    workflow_name=row["workflow_name"],
                    total_runs=row["total_runs"],
                    successful_runs=row["successful_runs"] or 0,
                    avg_rating=float(row["avg_rating"]) if row["avg_rating"] else None,
                    last_used=row["last_used"],
                )
            )

        return stats

    async def get_recent_runs(self, limit: int = 10) -> list[WorkflowRun]:
        """Get the most recent workflow runs."""
        await self.initialize()
        pool = await self._ensure_pool()

        rows = await pool.fetch(
            """
            SELECT * FROM workflow_runs
            ORDER BY started_at DESC
            LIMIT $1
            """,
            limit,
        )

        return [self._row_to_run(row) for row in rows]

    async def get_runs_for_workflow(self, workflow_name: str, limit: int = 10) -> list[WorkflowRun]:
        """Get recent runs for a specific workflow."""
        await self.initialize()
        pool = await self._ensure_pool()

        rows = await pool.fetch(
            """
            SELECT * FROM workflow_runs
            WHERE workflow_name = $1
            ORDER BY started_at DESC
            LIMIT $2
            """,
            workflow_name,
            limit,
        )

        return [self._row_to_run(row) for row in rows]

    def _row_to_run(self, row: asyncpg.Record) -> WorkflowRun:
        """Convert a database row to a WorkflowRun."""
        return WorkflowRun(
            id=row["id"],
            workflow_name=row["workflow_name"],
            goal=row["goal"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            success=row["success"],
            user_rating=row["user_rating"],
            tokens_used=row["tokens_used"] or 0,
            error=row["error"],
            output=row["output"],
        )

    # =========================================================================
    # Task Execution Tracking
    # =========================================================================

    async def record_task_execution(self, execution: TaskExecution) -> None:
        """Record a task execution."""
        await self.initialize()
        pool = await self._ensure_pool()

        # Serialize output to JSON string if it's not already a string
        import json

        output_str = None
        if execution.output is not None:
            if isinstance(execution.output, str):
                output_str = execution.output
            else:
                output_str = json.dumps(execution.output, ensure_ascii=False, default=str)

        await pool.execute(
            """
            INSERT INTO workflow_task_executions
            (id, run_id, task_definition_id, task_name, execution_order,
             state, started_at, completed_at, output, error)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (id) DO UPDATE SET
                state = EXCLUDED.state,
                completed_at = EXCLUDED.completed_at,
                output = EXCLUDED.output,
                error = EXCLUDED.error
            """,
            execution.id,
            execution.run_id,
            execution.task_definition_id,
            execution.task_name,
            execution.execution_order,
            execution.state,
            execution.started_at,
            execution.completed_at,
            output_str,
            execution.error,
        )

    async def record_task_executions(self, executions: list[TaskExecution]) -> None:
        """Record multiple task executions in batch."""
        for execution in executions:
            await self.record_task_execution(execution)

    async def get_task_executions(self, run_id: str) -> list[TaskExecution]:
        """Get all task executions for a workflow run, ordered by execution order."""
        await self.initialize()
        pool = await self._ensure_pool()

        rows = await pool.fetch(
            """
            SELECT * FROM workflow_task_executions
            WHERE run_id = $1
            ORDER BY execution_order ASC
            """,
            run_id,
        )

        return [self._row_to_task_execution(row) for row in rows]

    def _row_to_task_execution(self, row: asyncpg.Record) -> TaskExecution:
        """Convert a database row to a TaskExecution."""
        import json

        # Parse output from JSON string if present
        output = row["output"]
        if output is not None:
            try:
                output = json.loads(output)
            except (json.JSONDecodeError, TypeError):
                # Keep as string if not valid JSON
                pass

        return TaskExecution(
            id=row["id"],
            run_id=row["run_id"],
            task_definition_id=row["task_definition_id"],
            task_name=row["task_name"],
            execution_order=row["execution_order"],
            state=row["state"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            output=output,
            error=row["error"],
        )
