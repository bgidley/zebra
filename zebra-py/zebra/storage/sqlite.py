"""SQLite storage implementation for persistent workflows."""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite

from zebra.core.models import (
    FlowOfExecution,
    ProcessDefinition,
    ProcessInstance,
    ProcessState,
    TaskInstance,
    TaskState,
)
from zebra.storage.base import StateStore


class SQLiteStore(StateStore):
    """SQLite-based persistent storage for workflows.

    Stores runtime state (processes, tasks, FOEs) in SQLite and
    workflow definitions as JSON for human readability.

    This is the default storage backend for production use.
    """

    def __init__(self, db_path: str | Path = "zebra_workflows.db") -> None:
        self.db_path = Path(db_path)
        self._conn: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Create database tables if they don't exist."""
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row

        await self._conn.executescript(
            """
            -- Process Definitions (stored as JSON for flexibility)
            CREATE TABLE IF NOT EXISTS process_definitions (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                data JSON NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            -- Process Instances
            CREATE TABLE IF NOT EXISTS process_instances (
                id TEXT PRIMARY KEY,
                definition_id TEXT NOT NULL,
                state TEXT NOT NULL,
                properties JSON NOT NULL DEFAULT '{}',
                parent_process_id TEXT,
                parent_task_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                FOREIGN KEY (definition_id) REFERENCES process_definitions(id)
            );

            -- Task Instances
            CREATE TABLE IF NOT EXISTS task_instances (
                id TEXT PRIMARY KEY,
                process_id TEXT NOT NULL,
                task_definition_id TEXT NOT NULL,
                state TEXT NOT NULL,
                foe_id TEXT NOT NULL,
                properties JSON NOT NULL DEFAULT '{}',
                result JSON,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                FOREIGN KEY (process_id) REFERENCES process_instances(id)
            );

            -- Flow of Execution tracking
            CREATE TABLE IF NOT EXISTS foes (
                id TEXT PRIMARY KEY,
                process_id TEXT NOT NULL,
                parent_foe_id TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (process_id) REFERENCES process_instances(id)
            );

            -- Process Locks
            CREATE TABLE IF NOT EXISTS process_locks (
                process_id TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                acquired_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );

            -- Indexes for common queries
            CREATE INDEX IF NOT EXISTS idx_processes_definition ON process_instances(definition_id);
            CREATE INDEX IF NOT EXISTS idx_processes_state ON process_instances(state);
            CREATE INDEX IF NOT EXISTS idx_tasks_process ON task_instances(process_id);
            CREATE INDEX IF NOT EXISTS idx_tasks_state ON task_instances(state);
            CREATE INDEX IF NOT EXISTS idx_foes_process ON foes(process_id);
            """
        )
        await self._conn.commit()

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    def _ensure_connected(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Store not initialized. Call initialize() first.")
        return self._conn

    # =========================================================================
    # Process Definition Operations
    # =========================================================================

    async def save_definition(self, definition: ProcessDefinition) -> None:
        conn = self._ensure_connected()
        data = definition.model_dump_json()
        await conn.execute(
            """
            INSERT INTO process_definitions (id, name, version, data, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                version = excluded.version,
                data = excluded.data,
                updated_at = CURRENT_TIMESTAMP
            """,
            (definition.id, definition.name, definition.version, data),
        )
        await conn.commit()

    async def load_definition(self, definition_id: str) -> ProcessDefinition | None:
        conn = self._ensure_connected()
        cursor = await conn.execute(
            "SELECT data FROM process_definitions WHERE id = ?", (definition_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return ProcessDefinition.model_validate_json(row["data"])

    async def list_definitions(self) -> list[ProcessDefinition]:
        conn = self._ensure_connected()
        cursor = await conn.execute("SELECT data FROM process_definitions ORDER BY name")
        rows = await cursor.fetchall()
        return [ProcessDefinition.model_validate_json(row["data"]) for row in rows]

    async def delete_definition(self, definition_id: str) -> bool:
        conn = self._ensure_connected()
        cursor = await conn.execute(
            "DELETE FROM process_definitions WHERE id = ?", (definition_id,)
        )
        await conn.commit()
        return cursor.rowcount > 0

    # =========================================================================
    # Process Instance Operations
    # =========================================================================

    async def save_process(self, process: ProcessInstance) -> None:
        conn = self._ensure_connected()
        await conn.execute(
            """
            INSERT INTO process_instances
                (id, definition_id, state, properties, parent_process_id, parent_task_id,
                 created_at, updated_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                state = excluded.state,
                properties = excluded.properties,
                updated_at = excluded.updated_at,
                completed_at = excluded.completed_at
            """,
            (
                process.id,
                process.definition_id,
                process.state.value,
                json.dumps(process.properties),
                process.parent_process_id,
                process.parent_task_id,
                process.created_at.isoformat(),
                process.updated_at.isoformat(),
                process.completed_at.isoformat() if process.completed_at else None,
            ),
        )
        await conn.commit()

    async def load_process(self, process_id: str) -> ProcessInstance | None:
        conn = self._ensure_connected()
        cursor = await conn.execute("SELECT * FROM process_instances WHERE id = ?", (process_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_process(row)

    async def list_processes(
        self, definition_id: str | None = None, include_completed: bool = False
    ) -> list[ProcessInstance]:
        conn = self._ensure_connected()
        query = "SELECT * FROM process_instances WHERE 1=1"
        params: list[Any] = []

        if definition_id:
            query += " AND definition_id = ?"
            params.append(definition_id)

        if not include_completed:
            query += " AND state NOT IN (?, ?)"
            params.extend([ProcessState.COMPLETE.value, ProcessState.FAILED.value])

        query += " ORDER BY created_at DESC"

        cursor = await conn.execute(query, params)
        rows = await cursor.fetchall()
        return [self._row_to_process(row) for row in rows]

    async def delete_process(self, process_id: str) -> bool:
        conn = self._ensure_connected()
        # Delete in order respecting foreign keys
        await conn.execute("DELETE FROM task_instances WHERE process_id = ?", (process_id,))
        await conn.execute("DELETE FROM foes WHERE process_id = ?", (process_id,))
        await conn.execute("DELETE FROM process_locks WHERE process_id = ?", (process_id,))
        cursor = await conn.execute("DELETE FROM process_instances WHERE id = ?", (process_id,))
        await conn.commit()
        return cursor.rowcount > 0

    async def get_running_processes(self) -> list[ProcessInstance]:
        """Get all processes in RUNNING state (excluding PAUSED)."""
        conn = self._ensure_connected()
        cursor = await conn.execute(
            """
            SELECT * FROM process_instances 
            WHERE state = ?
            ORDER BY created_at DESC
            """,
            (ProcessState.RUNNING.value,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_process(row) for row in rows]

    def _row_to_process(self, row: aiosqlite.Row) -> ProcessInstance:
        return ProcessInstance(
            id=row["id"],
            definition_id=row["definition_id"],
            state=ProcessState(row["state"]),
            properties=json.loads(row["properties"]),
            parent_process_id=row["parent_process_id"],
            parent_task_id=row["parent_task_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            completed_at=datetime.fromisoformat(row["completed_at"])
            if row["completed_at"]
            else None,
        )

    # =========================================================================
    # Task Instance Operations
    # =========================================================================

    async def save_task(self, task: TaskInstance) -> None:
        conn = self._ensure_connected()
        await conn.execute(
            """
            INSERT INTO task_instances
                (id, process_id, task_definition_id, state, foe_id, properties,
                 result, error, created_at, updated_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                state = excluded.state,
                properties = excluded.properties,
                result = excluded.result,
                error = excluded.error,
                updated_at = excluded.updated_at,
                completed_at = excluded.completed_at
            """,
            (
                task.id,
                task.process_id,
                task.task_definition_id,
                task.state.value,
                task.foe_id,
                json.dumps(task.properties),
                json.dumps(task.result) if task.result is not None else None,
                task.error,
                task.created_at.isoformat(),
                task.updated_at.isoformat(),
                task.completed_at.isoformat() if task.completed_at else None,
            ),
        )
        await conn.commit()

    async def load_task(self, task_id: str) -> TaskInstance | None:
        conn = self._ensure_connected()
        cursor = await conn.execute("SELECT * FROM task_instances WHERE id = ?", (task_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_task(row)

    async def load_tasks_for_process(self, process_id: str) -> list[TaskInstance]:
        conn = self._ensure_connected()
        cursor = await conn.execute(
            "SELECT * FROM task_instances WHERE process_id = ? ORDER BY created_at",
            (process_id,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_task(row) for row in rows]

    async def delete_task(self, task_id: str) -> bool:
        conn = self._ensure_connected()
        cursor = await conn.execute("DELETE FROM task_instances WHERE id = ?", (task_id,))
        await conn.commit()
        return cursor.rowcount > 0

    async def get_running_tasks(self, process_id: str | None = None) -> list[TaskInstance]:
        """Get all tasks in RUNNING state, optionally filtered by process_id."""
        conn = self._ensure_connected()
        query = "SELECT * FROM task_instances WHERE state = ?"
        params: list[Any] = [TaskState.RUNNING.value]

        if process_id:
            query += " AND process_id = ?"
            params.append(process_id)

        query += " ORDER BY created_at"

        cursor = await conn.execute(query, params)
        rows = await cursor.fetchall()
        return [self._row_to_task(row) for row in rows]

    def _row_to_task(self, row: aiosqlite.Row) -> TaskInstance:
        return TaskInstance(
            id=row["id"],
            process_id=row["process_id"],
            task_definition_id=row["task_definition_id"],
            state=TaskState(row["state"]),
            foe_id=row["foe_id"],
            properties=json.loads(row["properties"]),
            result=json.loads(row["result"]) if row["result"] else None,
            error=row["error"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            completed_at=datetime.fromisoformat(row["completed_at"])
            if row["completed_at"]
            else None,
        )

    # =========================================================================
    # Flow of Execution Operations
    # =========================================================================

    async def save_foe(self, foe: FlowOfExecution) -> None:
        conn = self._ensure_connected()
        await conn.execute(
            """
            INSERT INTO foes (id, process_id, parent_foe_id, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (foe.id, foe.process_id, foe.parent_foe_id, foe.created_at.isoformat()),
        )
        await conn.commit()

    async def load_foe(self, foe_id: str) -> FlowOfExecution | None:
        conn = self._ensure_connected()
        cursor = await conn.execute("SELECT * FROM foes WHERE id = ?", (foe_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return FlowOfExecution(
            id=row["id"],
            process_id=row["process_id"],
            parent_foe_id=row["parent_foe_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    async def load_foes_for_process(self, process_id: str) -> list[FlowOfExecution]:
        conn = self._ensure_connected()
        cursor = await conn.execute(
            "SELECT * FROM foes WHERE process_id = ? ORDER BY created_at", (process_id,)
        )
        rows = await cursor.fetchall()
        return [
            FlowOfExecution(
                id=row["id"],
                process_id=row["process_id"],
                parent_foe_id=row["parent_foe_id"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    async def delete_foe(self, foe_id: str) -> bool:
        """Delete a flow of execution. Returns True if deleted."""
        conn = self._ensure_connected()
        cursor = await conn.execute("DELETE FROM foes WHERE id = ?", (foe_id,))
        await conn.commit()
        return cursor.rowcount > 0

    # =========================================================================
    # Locking Operations
    # =========================================================================

    async def acquire_lock(
        self, process_id: str, owner: str, timeout_seconds: float = 30.0
    ) -> bool:
        """Acquire a lock using SQLite with expiration-based timeout."""
        conn = self._ensure_connected()
        deadline = time.time() + timeout_seconds
        lock_duration = 60.0  # Lock expires after 60 seconds

        while time.time() < deadline:
            now = datetime.now(UTC).isoformat()
            expires_at = datetime.fromtimestamp(time.time() + lock_duration, tz=UTC).isoformat()

            # Try to insert new lock or take over expired lock
            try:
                await conn.execute(
                    """
                    INSERT INTO process_locks (process_id, owner, acquired_at, expires_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(process_id) DO UPDATE SET
                        owner = excluded.owner,
                        acquired_at = excluded.acquired_at,
                        expires_at = excluded.expires_at
                    WHERE process_locks.owner = excluded.owner
                        OR process_locks.expires_at < ?
                    """,
                    (process_id, owner, now, expires_at, now),
                )
                await conn.commit()

                # Check if we got the lock
                cursor = await conn.execute(
                    "SELECT owner FROM process_locks WHERE process_id = ?", (process_id,)
                )
                row = await cursor.fetchone()
                if row and row["owner"] == owner:
                    return True

            except Exception:
                pass

            # Wait before retrying
            await asyncio.sleep(0.1)

        return False

    async def release_lock(self, process_id: str, owner: str) -> bool:
        """Release a lock only if owned by the specified owner."""
        conn = self._ensure_connected()
        cursor = await conn.execute(
            "DELETE FROM process_locks WHERE process_id = ? AND owner = ?",
            (process_id, owner),
        )
        await conn.commit()
        return cursor.rowcount > 0

    # =========================================================================
    # Transaction Support
    # =========================================================================

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        """Wrap operations in a transaction."""
        conn = self._ensure_connected()
        try:
            yield
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
