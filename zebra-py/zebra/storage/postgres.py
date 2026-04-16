"""PostgreSQL storage implementation for persistent workflows."""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg

from zebra.core.exceptions import SerializationError
from zebra.core.models import (
    FlowOfExecution,
    ProcessDefinition,
    ProcessInstance,
    ProcessState,
    TaskInstance,
    TaskState,
)
from zebra.storage.base import StateStore


def _serialize_json(data: Any, context: str) -> str:
    """Serialize data to JSON, raising SerializationError on failure.

    Args:
        data: The data to serialize.
        context: Description for error messages (e.g., "process 'abc123' properties").

    Raises:
        SerializationError: If the data is not JSON-serializable.
    """
    try:
        return json.dumps(data)
    except (TypeError, ValueError) as e:
        raise SerializationError(
            f"Failed to serialize {context}: {e}. "
            f"All property values must be JSON-serializable "
            f"(strings, numbers, booleans, lists, dicts, and None)."
        ) from e


# PostgreSQL schema for all workflow state tables
SCHEMA_SQL = """
-- Process Definitions
CREATE TABLE IF NOT EXISTS process_definitions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Process Instances
CREATE TABLE IF NOT EXISTS process_instances (
    id TEXT PRIMARY KEY,
    definition_id TEXT NOT NULL REFERENCES process_definitions(id),
    state TEXT NOT NULL,
    properties JSONB NOT NULL DEFAULT '{}',
    parent_process_id TEXT REFERENCES process_instances(id),
    parent_task_id TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ
);

-- Task Instances
CREATE TABLE IF NOT EXISTS task_instances (
    id TEXT PRIMARY KEY,
    process_id TEXT NOT NULL REFERENCES process_instances(id) ON DELETE CASCADE,
    task_definition_id TEXT NOT NULL,
    state TEXT NOT NULL,
    foe_id TEXT NOT NULL,
    properties JSONB NOT NULL DEFAULT '{}',
    result JSONB,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ
);

-- Flow of Execution
CREATE TABLE IF NOT EXISTS foes (
    id TEXT PRIMARY KEY,
    process_id TEXT NOT NULL REFERENCES process_instances(id) ON DELETE CASCADE,
    parent_foe_id TEXT,
    created_at TIMESTAMPTZ NOT NULL
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_processes_definition ON process_instances(definition_id);
CREATE INDEX IF NOT EXISTS idx_processes_state ON process_instances(state);
CREATE INDEX IF NOT EXISTS idx_processes_created ON process_instances(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_process ON task_instances(process_id);
CREATE INDEX IF NOT EXISTS idx_tasks_state ON task_instances(state);
CREATE INDEX IF NOT EXISTS idx_foes_process ON foes(process_id);
"""


class PostgreSQLStore(StateStore):
    """PostgreSQL-based persistent storage for workflows.

    Uses asyncpg for high-performance async database operations.
    Stores all workflow state in PostgreSQL with proper relational integrity.

    This is the default storage backend for production use.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "opc",
        user: str = "opc",
        password: str | None = None,
        min_pool_size: int = 2,
        max_pool_size: int = 10,
    ) -> None:
        """Initialize PostgreSQL store with connection parameters.

        Args:
            host: Database host (default: localhost)
            port: Database port (default: 5432)
            database: Database name (default: opc)
            user: Database user (default: opc)
            password: Database password (optional, uses peer auth if None)
            min_pool_size: Minimum connections in pool (default: 2)
            max_pool_size: Maximum connections in pool (default: 10)
        """
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.min_pool_size = min_pool_size
        self.max_pool_size = max_pool_size
        self._pool: asyncpg.Pool | None = None

    async def initialize(self) -> None:
        """Create connection pool and initialize schema."""
        # Create connection pool
        self._pool = await asyncpg.create_pool(
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
            password=self.password,
            min_size=self.min_pool_size,
            max_size=self.max_pool_size,
        )

        # Initialize schema
        async with self._pool.acquire() as conn:
            await conn.execute(SCHEMA_SQL)

    async def close(self) -> None:
        """Close connection pool and release resources."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    def _ensure_pool(self) -> asyncpg.Pool:
        """Ensure pool is initialized."""
        if self._pool is None:
            raise RuntimeError("Store not initialized. Call initialize() first.")
        return self._pool

    # =========================================================================
    # Process Definition Operations
    # =========================================================================

    async def save_definition(self, definition: ProcessDefinition) -> None:
        """Save or update a process definition."""
        pool = self._ensure_pool()
        data = definition.model_dump_json()
        await pool.execute(
            """
            INSERT INTO process_definitions (id, name, version, data)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                version = EXCLUDED.version,
                data = EXCLUDED.data,
                updated_at = CURRENT_TIMESTAMP
            """,
            definition.id,
            definition.name,
            definition.version,
            data,
        )

    async def load_definition(self, definition_id: str) -> ProcessDefinition | None:
        """Load a process definition by ID. Returns None if not found."""
        pool = self._ensure_pool()
        row = await pool.fetchrow(
            "SELECT data FROM process_definitions WHERE id = $1", definition_id
        )
        if row is None:
            return None
        return ProcessDefinition.model_validate_json(row["data"])

    async def list_definitions(self) -> list[ProcessDefinition]:
        """List all available process definitions."""
        pool = self._ensure_pool()
        rows = await pool.fetch("SELECT data FROM process_definitions ORDER BY name")
        return [ProcessDefinition.model_validate_json(row["data"]) for row in rows]

    async def delete_definition(self, definition_id: str) -> bool:
        """Delete a process definition. Returns True if deleted, False if not found."""
        pool = self._ensure_pool()
        result = await pool.execute("DELETE FROM process_definitions WHERE id = $1", definition_id)
        # Result format: "DELETE N" where N is number of rows
        return int(result.split()[-1]) > 0

    # =========================================================================
    # Process Instance Operations
    # =========================================================================

    async def save_process(self, process: ProcessInstance) -> None:
        """Save or update a process instance."""
        pool = self._ensure_pool()
        await pool.execute(
            """
            INSERT INTO process_instances
                (id, definition_id, state, properties, parent_process_id, parent_task_id,
                 created_at, updated_at, completed_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (id) DO UPDATE SET
                state = EXCLUDED.state,
                properties = EXCLUDED.properties,
                updated_at = EXCLUDED.updated_at,
                completed_at = EXCLUDED.completed_at
            """,
            process.id,
            process.definition_id,
            process.state.value,
            _serialize_json(process.properties, f"process '{process.id}' properties"),
            process.parent_process_id,
            process.parent_task_id,
            process.created_at,
            process.updated_at,
            process.completed_at,
        )

    async def load_process(self, process_id: str) -> ProcessInstance | None:
        """Load a process instance by ID. Returns None if not found."""
        pool = self._ensure_pool()
        row = await pool.fetchrow("SELECT * FROM process_instances WHERE id = $1", process_id)
        if row is None:
            return None
        return self._row_to_process(row)

    async def list_processes(
        self, definition_id: str | None = None, include_completed: bool = False
    ) -> list[ProcessInstance]:
        """List process instances, optionally filtered by definition and completion status."""
        pool = self._ensure_pool()
        conditions = []
        params: list[Any] = []
        param_idx = 1

        if definition_id:
            conditions.append(f"definition_id = ${param_idx}")
            params.append(definition_id)
            param_idx += 1

        if not include_completed:
            conditions.append(f"state NOT IN (${param_idx}, ${param_idx + 1})")
            params.extend([ProcessState.COMPLETE.value, ProcessState.FAILED.value])
            param_idx += 2

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        query = f"SELECT * FROM process_instances {where_clause} ORDER BY created_at DESC"

        rows = await pool.fetch(query, *params)
        return [self._row_to_process(row) for row in rows]

    async def delete_process(self, process_id: str) -> bool:
        """Delete a process instance and all related data. Returns True if deleted."""
        pool = self._ensure_pool()
        # Cascade deletes will handle tasks and FOEs automatically
        result = await pool.execute("DELETE FROM process_instances WHERE id = $1", process_id)
        return int(result.split()[-1]) > 0

    async def get_running_processes(self) -> list[ProcessInstance]:
        """Get all processes in RUNNING state (excluding PAUSED)."""
        pool = self._ensure_pool()
        rows = await pool.fetch(
            """
            SELECT * FROM process_instances 
            WHERE state = $1
            ORDER BY created_at DESC
            """,
            ProcessState.RUNNING.value,
        )
        return [self._row_to_process(row) for row in rows]

    async def get_processes_by_state(
        self,
        state: ProcessState,
        exclude_children: bool = False,
    ) -> list[ProcessInstance]:
        """Get processes in a specific state, ordered by created_at ascending."""
        pool = self._ensure_pool()
        if exclude_children:
            rows = await pool.fetch(
                """
                SELECT * FROM process_instances
                WHERE state = $1 AND parent_process_id IS NULL
                ORDER BY created_at ASC
                """,
                state.value,
            )
        else:
            rows = await pool.fetch(
                """
                SELECT * FROM process_instances
                WHERE state = $1
                ORDER BY created_at ASC
                """,
                state.value,
            )
        return [self._row_to_process(row) for row in rows]

    def _row_to_process(self, row: asyncpg.Record) -> ProcessInstance:
        """Convert database row to ProcessInstance."""
        return ProcessInstance(
            id=row["id"],
            definition_id=row["definition_id"],
            state=ProcessState(row["state"]),
            properties=json.loads(row["properties"])
            if isinstance(row["properties"], str)
            else row["properties"],
            parent_process_id=row["parent_process_id"],
            parent_task_id=row["parent_task_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
        )

    # =========================================================================
    # Task Instance Operations
    # =========================================================================

    async def save_task(self, task: TaskInstance) -> None:
        """Save or update a task instance."""
        pool = self._ensure_pool()
        await pool.execute(
            """
            INSERT INTO task_instances
                (id, process_id, task_definition_id, state, foe_id, properties,
                 result, error, created_at, updated_at, completed_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (id) DO UPDATE SET
                state = EXCLUDED.state,
                properties = EXCLUDED.properties,
                result = EXCLUDED.result,
                error = EXCLUDED.error,
                updated_at = EXCLUDED.updated_at,
                completed_at = EXCLUDED.completed_at
            """,
            task.id,
            task.process_id,
            task.task_definition_id,
            task.state.value,
            task.foe_id,
            _serialize_json(task.properties, f"task '{task.id}' properties"),
            _serialize_json(task.result, f"task '{task.id}' result")
            if task.result is not None
            else None,
            task.error,
            task.created_at,
            task.updated_at,
            task.completed_at,
        )

    async def load_task(self, task_id: str) -> TaskInstance | None:
        """Load a task instance by ID. Returns None if not found."""
        pool = self._ensure_pool()
        row = await pool.fetchrow("SELECT * FROM task_instances WHERE id = $1", task_id)
        if row is None:
            return None
        return self._row_to_task(row)

    async def load_tasks_for_process(self, process_id: str) -> list[TaskInstance]:
        """Load all task instances for a process."""
        pool = self._ensure_pool()
        rows = await pool.fetch(
            "SELECT * FROM task_instances WHERE process_id = $1 ORDER BY created_at",
            process_id,
        )
        return [self._row_to_task(row) for row in rows]

    async def delete_task(self, task_id: str) -> bool:
        """Delete a task instance. Returns True if deleted."""
        pool = self._ensure_pool()
        result = await pool.execute("DELETE FROM task_instances WHERE id = $1", task_id)
        return int(result.split()[-1]) > 0

    async def get_running_tasks(self, process_id: str | None = None) -> list[TaskInstance]:
        """Get all tasks in RUNNING state, optionally filtered by process_id."""
        pool = self._ensure_pool()
        conditions: list[str] = ["state = $1"]
        params: list[Any] = [TaskState.RUNNING.value]
        param_count = 2

        if process_id:
            conditions.append(f"process_id = ${param_count}")
            params.append(process_id)
            param_count += 1

        where_clause = "WHERE " + " AND ".join(conditions)
        query = f"SELECT * FROM task_instances {where_clause} ORDER BY created_at"

        rows = await pool.fetch(query, *params)
        return [self._row_to_task(row) for row in rows]

    def _row_to_task(self, row: asyncpg.Record) -> TaskInstance:
        """Convert database row to TaskInstance."""
        return TaskInstance(
            id=row["id"],
            process_id=row["process_id"],
            task_definition_id=row["task_definition_id"],
            state=TaskState(row["state"]),
            foe_id=row["foe_id"],
            properties=json.loads(row["properties"])
            if isinstance(row["properties"], str)
            else row["properties"],
            result=json.loads(row["result"])
            if row["result"] and isinstance(row["result"], str)
            else row["result"],
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
        )

    # =========================================================================
    # Flow of Execution Operations
    # =========================================================================

    async def save_foe(self, foe: FlowOfExecution) -> None:
        """Save or update a flow of execution."""
        pool = self._ensure_pool()
        await pool.execute(
            """
            INSERT INTO foes (id, process_id, parent_foe_id, created_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (id) DO NOTHING
            """,
            foe.id,
            foe.process_id,
            foe.parent_foe_id,
            foe.created_at,
        )

    async def load_foe(self, foe_id: str) -> FlowOfExecution | None:
        """Load a flow of execution by ID. Returns None if not found."""
        pool = self._ensure_pool()
        row = await pool.fetchrow("SELECT * FROM foes WHERE id = $1", foe_id)
        if row is None:
            return None
        return FlowOfExecution(
            id=row["id"],
            process_id=row["process_id"],
            parent_foe_id=row["parent_foe_id"],
            created_at=row["created_at"],
        )

    async def load_foes_for_process(self, process_id: str) -> list[FlowOfExecution]:
        """Load all FOEs for a process."""
        pool = self._ensure_pool()
        rows = await pool.fetch(
            "SELECT * FROM foes WHERE process_id = $1 ORDER BY created_at", process_id
        )
        return [
            FlowOfExecution(
                id=row["id"],
                process_id=row["process_id"],
                parent_foe_id=row["parent_foe_id"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    async def delete_foe(self, foe_id: str) -> bool:
        """Delete a flow of execution. Returns True if deleted."""
        pool = self._ensure_pool()
        result = await pool.execute("DELETE FROM foes WHERE id = $1", foe_id)
        # Result format: "DELETE N" where N is number of rows
        return int(result.split()[-1]) > 0

    # =========================================================================
    # Locking Operations
    # =========================================================================

    async def acquire_lock(
        self, process_id: str, owner: str, timeout_seconds: float = 30.0
    ) -> bool:
        """Acquire an exclusive lock on a process instance using PostgreSQL advisory locks.

        Args:
            process_id: The process to lock
            owner: Identifier for the lock owner (e.g., engine instance ID)
            timeout_seconds: How long to wait for lock acquisition

        Returns:
            True if lock acquired, False if timeout
        """
        pool = self._ensure_pool()
        # Convert process_id to integer hash for advisory lock
        # Use only lower 31 bits to ensure positive integer for PostgreSQL
        lock_id = hash(process_id) % (2**31)
        deadline = time.time() + timeout_seconds

        while time.time() < deadline:
            async with pool.acquire() as conn:
                # Try to acquire advisory lock
                acquired = await conn.fetchval("SELECT pg_try_advisory_lock($1)", lock_id)
                if acquired:
                    return True

            # Wait before retrying
            await asyncio.sleep(0.1)

        return False

    async def release_lock(self, process_id: str, owner: str) -> bool:
        """Release a lock on a process instance.

        Args:
            process_id: The process to unlock
            owner: Must match the owner that acquired the lock (not enforced by advisory locks)

        Returns:
            True if released, False if not locked
        """
        pool = self._ensure_pool()
        lock_id = hash(process_id) % (2**31)

        async with pool.acquire() as conn:
            released = await conn.fetchval("SELECT pg_advisory_unlock($1)", lock_id)
            return bool(released)

    # =========================================================================
    # Transaction Support
    # =========================================================================

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        """Context manager for transactional operations.

        Usage:
            async with store.transaction():
                await store.save_process(process)
                await store.save_task(task)
                # Commits automatically, or rolls back on exception
        """
        pool = self._ensure_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                yield
