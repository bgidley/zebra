"""Oracle database storage implementation for persistent workflows.

This module provides Oracle database support for the Zebra workflow engine,
designed for Oracle 21c+ (including Oracle Cloud Autonomous Database).

Uses the python-oracledb driver in thin mode for async operations.
"""

import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import oracledb

from zebra.core.models import (
    FlowOfExecution,
    ProcessDefinition,
    ProcessInstance,
    ProcessState,
    TaskInstance,
    TaskState,
)
from zebra.storage.base import StateStore

logger = logging.getLogger(__name__)


async def _read_clob_async(value: Any) -> str | None:
    """Safely read a CLOB value from Oracle asynchronously.

    Handles cases where the value might be:
    - Already a string
    - An AsyncLOB object with async .read()
    - A file-like object with sync .read()
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
        result = value.read()
        # Handle async LOB objects (coroutines)
        if asyncio.iscoroutine(result):
            return await result
        return result
    return str(value)


def _read_clob(value: Any) -> str | None:
    """Safely read a CLOB value from Oracle (sync version for non-LOB data).

    NOTE: This function cannot handle AsyncLOB objects. Use _read_clob_async
    for data that may contain LOB objects from async queries.

    Handles cases where the value might be:
    - Already a string
    - A dict (JSON data)
    - None
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return json.dumps(value)
    # Don't call .read() here as it may return a coroutine
    return str(value)


# Oracle schema for all workflow state tables (Oracle 21c+ with native JSON)
SCHEMA_SQL = """
-- Process Definitions
CREATE TABLE process_definitions (
    id VARCHAR2(255) PRIMARY KEY,
    name VARCHAR2(255) NOT NULL,
    version NUMBER DEFAULT 1 NOT NULL,
    data CLOB NOT NULL CHECK (data IS JSON),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""

SCHEMA_PROCESS_INSTANCES = """
CREATE TABLE process_instances (
    id VARCHAR2(255) PRIMARY KEY,
    definition_id VARCHAR2(255) NOT NULL REFERENCES process_definitions(id),
    state VARCHAR2(50) NOT NULL,
    properties CLOB DEFAULT '{}' NOT NULL CHECK (properties IS JSON),
    parent_process_id VARCHAR2(255) REFERENCES process_instances(id),
    parent_task_id VARCHAR2(255),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE
)
"""

SCHEMA_TASK_INSTANCES = """
CREATE TABLE task_instances (
    id VARCHAR2(255) PRIMARY KEY,
    process_id VARCHAR2(255) NOT NULL REFERENCES process_instances(id) ON DELETE CASCADE,
    task_definition_id VARCHAR2(255) NOT NULL,
    state VARCHAR2(50) NOT NULL,
    foe_id VARCHAR2(255) NOT NULL,
    properties CLOB DEFAULT '{}' NOT NULL CHECK (properties IS JSON),
    result CLOB CHECK (result IS JSON),
    error CLOB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE
)
"""

SCHEMA_FOES = """
CREATE TABLE foes (
    id VARCHAR2(255) PRIMARY KEY,
    process_id VARCHAR2(255) NOT NULL REFERENCES process_instances(id) ON DELETE CASCADE,
    parent_foe_id VARCHAR2(255),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
)
"""

SCHEMA_LOCKS = """
CREATE TABLE process_locks (
    process_id VARCHAR2(255) PRIMARY KEY,
    owner VARCHAR2(255) NOT NULL,
    acquired_at TIMESTAMP WITH TIME ZONE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
)
"""

# Index creation statements
SCHEMA_INDEXES = [
    "CREATE INDEX idx_processes_definition ON process_instances(definition_id)",
    "CREATE INDEX idx_processes_state ON process_instances(state)",
    "CREATE INDEX idx_processes_created ON process_instances(created_at DESC)",
    "CREATE INDEX idx_tasks_process ON task_instances(process_id)",
    "CREATE INDEX idx_tasks_state ON task_instances(state)",
    "CREATE INDEX idx_foes_process ON foes(process_id)",
]


class OracleStore(StateStore):
    """Oracle database storage for workflows.

    Uses python-oracledb for async database operations with Oracle 21c+.
    Stores all workflow state in Oracle with proper relational integrity.

    Designed for Oracle Cloud Autonomous Database but works with any Oracle 21c+.

    Example (without wallet - requires mTLS disabled in Oracle Cloud):
        >>> store = OracleStore(
        ...     user="ZEBRA",
        ...     password="secret",
        ...     dsn="(description=(address=(protocol=tcps)(port=1522)...))",
        ... )
        >>> await store.initialize()

    Example (with wallet - for Oracle Cloud ADB with mTLS enabled):
        >>> store = OracleStore(
        ...     user="ZEBRA",
        ...     password="secret",
        ...     dsn="zebra_high",  # TNS alias from tnsnames.ora in wallet
        ...     wallet_location="/path/to/wallet",
        ...     wallet_password="wallet_secret",  # Optional, for encrypted wallet
        ... )
        >>> await store.initialize()
    """

    def __init__(
        self,
        user: str | None = None,
        password: str | None = None,
        dsn: str | None = None,
        min_pool_size: int = 2,
        max_pool_size: int = 10,
        wallet_location: str | None = None,
        wallet_password: str | None = None,
    ) -> None:
        """Initialize Oracle store with connection parameters.

        Args:
            user: Database username (defaults to ORACLE_USERNAME env var)
            password: Database password (defaults to ORACLE_PASSWORD env var)
            dsn: Oracle connection string or TNS alias (defaults to ORACLE_DSN env var)
            min_pool_size: Minimum connections in pool (default: 2)
            max_pool_size: Maximum connections in pool (default: 10)
            wallet_location: Path to Oracle wallet directory (for mTLS).
                           Defaults to ORACLE_WALLET_LOCATION env var.
                           Required for Oracle Cloud ADB with mTLS enabled.
            wallet_password: Password for encrypted wallet.
                           Defaults to ORACLE_WALLET_PASSWORD env var.
                           Only needed if wallet is password-protected.

        Raises:
            ValueError: If required connection parameters are missing
        """
        self.user = user or os.environ.get("ORACLE_USERNAME")
        self.password = password or os.environ.get("ORACLE_PASSWORD")
        self.dsn = dsn or os.environ.get("ORACLE_DSN")
        self.wallet_location = wallet_location or os.environ.get("ORACLE_WALLET_LOCATION")
        self.wallet_password = wallet_password or os.environ.get("ORACLE_WALLET_PASSWORD")

        if not self.user:
            raise ValueError("Oracle user required (set ORACLE_USERNAME env var or pass user=)")
        if not self.password:
            raise ValueError(
                "Oracle password required (set ORACLE_PASSWORD env var or pass password=)"
            )
        if not self.dsn:
            raise ValueError("Oracle DSN required (set ORACLE_DSN env var or pass dsn=)")

        self.min_pool_size = min_pool_size
        self.max_pool_size = max_pool_size
        self._pool: oracledb.AsyncConnectionPool | None = None

    async def initialize(self) -> None:
        """Create connection pool and initialize schema."""
        # Build connection parameters
        pool_params: dict[str, Any] = {
            "user": self.user,
            "password": self.password,
            "dsn": self.dsn,
            "min": self.min_pool_size,
            "max": self.max_pool_size,
        }

        # Add wallet parameters for Oracle Cloud ADB with mTLS
        if self.wallet_location:
            pool_params["config_dir"] = self.wallet_location
            pool_params["wallet_location"] = self.wallet_location
            if self.wallet_password:
                pool_params["wallet_password"] = self.wallet_password

        # Create async connection pool
        self._pool = oracledb.create_pool_async(**pool_params)

        # Initialize schema (create tables if they don't exist)
        async with self._pool.acquire() as conn:
            await self._create_schema(conn)

    async def _create_schema(self, conn: oracledb.AsyncConnection) -> None:
        """Create database tables if they don't exist."""
        tables_and_sql = [
            ("process_definitions", SCHEMA_SQL),
            ("process_instances", SCHEMA_PROCESS_INSTANCES),
            ("task_instances", SCHEMA_TASK_INSTANCES),
            ("foes", SCHEMA_FOES),
            ("process_locks", SCHEMA_LOCKS),
        ]

        for table_name, create_sql in tables_and_sql:
            if not await self._table_exists(conn, table_name):
                async with conn.cursor() as cursor:
                    await cursor.execute(create_sql)
                logger.info("Created table: %s", table_name)

        # Create indexes (ignore errors if they already exist)
        for index_sql in SCHEMA_INDEXES:
            try:
                async with conn.cursor() as cursor:
                    await cursor.execute(index_sql)
            except oracledb.DatabaseError as e:
                # ORA-00955: name is already used by an existing object
                if "ORA-00955" not in str(e):
                    raise

        await conn.commit()

    async def _table_exists(self, conn: oracledb.AsyncConnection, table_name: str) -> bool:
        """Check if a table exists in the database."""
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT COUNT(*) FROM user_tables WHERE table_name = :1",
                [table_name.upper()],
            )
            row = await cursor.fetchone()
            return row[0] > 0 if row else False

    async def close(self) -> None:
        """Close connection pool and release resources."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    def _ensure_pool(self) -> oracledb.AsyncConnectionPool:
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

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # Use MERGE for upsert
                await cursor.execute(
                    """
                    MERGE INTO process_definitions d
                    USING (SELECT :1 AS id, :2 AS name, :3 AS version, :4 AS data FROM dual) s
                    ON (d.id = s.id)
                    WHEN MATCHED THEN
                        UPDATE SET name = s.name, version = s.version, data = s.data,
                                   updated_at = CURRENT_TIMESTAMP
                    WHEN NOT MATCHED THEN
                        INSERT (id, name, version, data)
                        VALUES (s.id, s.name, s.version, s.data)
                    """,
                    [definition.id, definition.name, definition.version, data],
                )
            await conn.commit()

    async def load_definition(self, definition_id: str) -> ProcessDefinition | None:
        """Load a process definition by ID. Returns None if not found."""
        pool = self._ensure_pool()

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "SELECT data FROM process_definitions WHERE id = :1",
                    [definition_id],
                )
                row = await cursor.fetchone()
                if row is None:
                    return None
                data = await _read_clob_async(row[0])
                return ProcessDefinition.model_validate_json(data or "{}")

    async def list_definitions(self) -> list[ProcessDefinition]:
        """List all available process definitions."""
        pool = self._ensure_pool()

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT data FROM process_definitions ORDER BY name")
                rows = await cursor.fetchall()
                return [
                    ProcessDefinition.model_validate_json(_read_clob(row[0]) or "{}")
                    for row in rows
                ]

    async def delete_definition(self, definition_id: str) -> bool:
        """Delete a process definition. Returns True if deleted, False if not found."""
        pool = self._ensure_pool()

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "DELETE FROM process_definitions WHERE id = :1",
                    [definition_id],
                )
                deleted = cursor.rowcount > 0
            await conn.commit()
            return deleted

    # =========================================================================
    # Process Instance Operations
    # =========================================================================

    async def save_process(self, process: ProcessInstance) -> None:
        """Save or update a process instance."""
        pool = self._ensure_pool()

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    MERGE INTO process_instances p
                    USING (SELECT :1 AS id, :2 AS definition_id, :3 AS state,
                                  :4 AS properties, :5 AS parent_process_id,
                                  :6 AS parent_task_id, :7 AS created_at,
                                  :8 AS updated_at, :9 AS completed_at FROM dual) s
                    ON (p.id = s.id)
                    WHEN MATCHED THEN
                        UPDATE SET state = s.state, properties = s.properties,
                                   updated_at = s.updated_at, completed_at = s.completed_at
                    WHEN NOT MATCHED THEN
                        INSERT (id, definition_id, state, properties, parent_process_id,
                                parent_task_id, created_at, updated_at, completed_at)
                        VALUES (s.id, s.definition_id, s.state, s.properties,
                                s.parent_process_id, s.parent_task_id, s.created_at,
                                s.updated_at, s.completed_at)
                    """,
                    [
                        process.id,
                        process.definition_id,
                        process.state.value,
                        json.dumps(process.properties),
                        process.parent_process_id,
                        process.parent_task_id,
                        process.created_at,
                        process.updated_at,
                        process.completed_at,
                    ],
                )
            await conn.commit()

    async def load_process(self, process_id: str) -> ProcessInstance | None:
        """Load a process instance by ID. Returns None if not found."""
        pool = self._ensure_pool()

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT id, definition_id, state, properties, parent_process_id,
                           parent_task_id, created_at, updated_at, completed_at
                    FROM process_instances WHERE id = :1
                    """,
                    [process_id],
                )
                row = await cursor.fetchone()
                if row is None:
                    return None
                return self._row_to_process(row)

    async def list_processes(
        self, definition_id: str | None = None, include_completed: bool = False
    ) -> list[ProcessInstance]:
        """List process instances, optionally filtered by definition and completion status."""
        pool = self._ensure_pool()

        query = """
            SELECT id, definition_id, state, properties, parent_process_id,
                   parent_task_id, created_at, updated_at, completed_at
            FROM process_instances WHERE 1=1
        """
        params: list[Any] = []
        param_idx = 1

        if definition_id:
            query += f" AND definition_id = :{param_idx}"
            params.append(definition_id)
            param_idx += 1

        if not include_completed:
            query += f" AND state NOT IN (:{param_idx}, :{param_idx + 1})"
            params.extend([ProcessState.COMPLETE.value, ProcessState.FAILED.value])
            param_idx += 2

        query += " ORDER BY created_at DESC"

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, params)
                rows = await cursor.fetchall()
                return [self._row_to_process(row) for row in rows]

    async def delete_process(self, process_id: str) -> bool:
        """Delete a process instance and all related data. Returns True if deleted."""
        pool = self._ensure_pool()

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # Delete locks first (no FK constraint)
                await cursor.execute(
                    "DELETE FROM process_locks WHERE process_id = :1", [process_id]
                )
                # Cascade deletes will handle tasks and FOEs automatically
                await cursor.execute("DELETE FROM process_instances WHERE id = :1", [process_id])
                deleted = cursor.rowcount > 0
            await conn.commit()
            return deleted

    async def get_running_processes(self) -> list[ProcessInstance]:
        """Get all processes in RUNNING state (excluding PAUSED)."""
        pool = self._ensure_pool()

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT id, definition_id, state, properties, parent_process_id,
                           parent_task_id, created_at, updated_at, completed_at
                    FROM process_instances
                    WHERE state = :1
                    ORDER BY created_at DESC
                    """,
                    [ProcessState.RUNNING.value],
                )
                rows = await cursor.fetchall()
                return [self._row_to_process(row) for row in rows]

    def _row_to_process(self, row: tuple) -> ProcessInstance:
        """Convert database row to ProcessInstance."""
        # Row order: id, definition_id, state, properties, parent_process_id,
        #            parent_task_id, created_at, updated_at, completed_at
        properties_data = _read_clob(row[3])
        properties = json.loads(properties_data) if properties_data else {}

        return ProcessInstance(
            id=row[0],
            definition_id=row[1],
            state=ProcessState(row[2]),
            properties=properties,
            parent_process_id=row[4],
            parent_task_id=row[5],
            created_at=row[6],
            updated_at=row[7],
            completed_at=row[8],
        )

    # =========================================================================
    # Task Instance Operations
    # =========================================================================

    async def save_task(self, task: TaskInstance) -> None:
        """Save or update a task instance."""
        pool = self._ensure_pool()

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    MERGE INTO task_instances t
                    USING (SELECT :1 AS id, :2 AS process_id, :3 AS task_definition_id,
                                  :4 AS state, :5 AS foe_id, :6 AS properties,
                                  :7 AS result, :8 AS error, :9 AS created_at,
                                  :10 AS updated_at, :11 AS completed_at FROM dual) s
                    ON (t.id = s.id)
                    WHEN MATCHED THEN
                        UPDATE SET state = s.state, properties = s.properties,
                                   result = s.result, error = s.error,
                                   updated_at = s.updated_at, completed_at = s.completed_at
                    WHEN NOT MATCHED THEN
                        INSERT (id, process_id, task_definition_id, state, foe_id,
                                properties, result, error, created_at, updated_at, completed_at)
                        VALUES (s.id, s.process_id, s.task_definition_id, s.state, s.foe_id,
                                s.properties, s.result, s.error, s.created_at, s.updated_at,
                                s.completed_at)
                    """,
                    [
                        task.id,
                        task.process_id,
                        task.task_definition_id,
                        task.state.value,
                        task.foe_id,
                        json.dumps(task.properties),
                        json.dumps(task.result) if task.result is not None else None,
                        task.error,
                        task.created_at,
                        task.updated_at,
                        task.completed_at,
                    ],
                )
            await conn.commit()

    async def load_task(self, task_id: str) -> TaskInstance | None:
        """Load a task instance by ID. Returns None if not found."""
        pool = self._ensure_pool()

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT id, process_id, task_definition_id, state, foe_id,
                           properties, result, error, created_at, updated_at, completed_at
                    FROM task_instances WHERE id = :1
                    """,
                    [task_id],
                )
                row = await cursor.fetchone()
                if row is None:
                    return None
                return self._row_to_task(row)

    async def load_tasks_for_process(self, process_id: str) -> list[TaskInstance]:
        """Load all task instances for a process."""
        pool = self._ensure_pool()

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT id, process_id, task_definition_id, state, foe_id,
                           properties, result, error, created_at, updated_at, completed_at
                    FROM task_instances
                    WHERE process_id = :1
                    ORDER BY created_at
                    """,
                    [process_id],
                )
                rows = await cursor.fetchall()
                return [self._row_to_task(row) for row in rows]

    async def delete_task(self, task_id: str) -> bool:
        """Delete a task instance. Returns True if deleted."""
        pool = self._ensure_pool()

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("DELETE FROM task_instances WHERE id = :1", [task_id])
                deleted = cursor.rowcount > 0
            await conn.commit()
            return deleted

    async def get_running_tasks(self, process_id: str | None = None) -> list[TaskInstance]:
        """Get all tasks in RUNNING state, optionally filtered by process_id."""
        pool = self._ensure_pool()

        query = """
            SELECT id, process_id, task_definition_id, state, foe_id,
                   properties, result, error, created_at, updated_at, completed_at
            FROM task_instances
            WHERE state = :1
        """
        params: list[Any] = [TaskState.RUNNING.value]

        if process_id:
            query += " AND process_id = :2"
            params.append(process_id)

        query += " ORDER BY created_at"

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, params)
                rows = await cursor.fetchall()
                return [self._row_to_task(row) for row in rows]

    def _row_to_task(self, row: tuple) -> TaskInstance:
        """Convert database row to TaskInstance."""
        # Row order: id, process_id, task_definition_id, state, foe_id,
        #            properties, result, error, created_at, updated_at, completed_at

        # Handle CLOB for properties
        properties_data = _read_clob(row[5])
        properties = json.loads(properties_data) if properties_data else {}

        # Handle CLOB for result
        result_data = _read_clob(row[6])
        result = json.loads(result_data) if result_data else None

        # Handle CLOB for error
        error_data = _read_clob(row[7])

        return TaskInstance(
            id=row[0],
            process_id=row[1],
            task_definition_id=row[2],
            state=TaskState(row[3]),
            foe_id=row[4],
            properties=properties,
            result=result,
            error=error_data,
            created_at=row[8],
            updated_at=row[9],
            completed_at=row[10],
        )

    # =========================================================================
    # Flow of Execution Operations
    # =========================================================================

    async def save_foe(self, foe: FlowOfExecution) -> None:
        """Save or update a flow of execution."""
        pool = self._ensure_pool()

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # Use MERGE with DO NOTHING equivalent for insert-only
                await cursor.execute(
                    """
                    MERGE INTO foes f
                    USING (SELECT :1 AS id, :2 AS process_id, :3 AS parent_foe_id,
                                  :4 AS created_at FROM dual) s
                    ON (f.id = s.id)
                    WHEN NOT MATCHED THEN
                        INSERT (id, process_id, parent_foe_id, created_at)
                        VALUES (s.id, s.process_id, s.parent_foe_id, s.created_at)
                    """,
                    [foe.id, foe.process_id, foe.parent_foe_id, foe.created_at],
                )
            await conn.commit()

    async def load_foe(self, foe_id: str) -> FlowOfExecution | None:
        """Load a flow of execution by ID. Returns None if not found."""
        pool = self._ensure_pool()

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "SELECT id, process_id, parent_foe_id, created_at FROM foes WHERE id = :1",
                    [foe_id],
                )
                row = await cursor.fetchone()
                if row is None:
                    return None
                return FlowOfExecution(
                    id=row[0],
                    process_id=row[1],
                    parent_foe_id=row[2],
                    created_at=row[3],
                )

    async def load_foes_for_process(self, process_id: str) -> list[FlowOfExecution]:
        """Load all FOEs for a process."""
        pool = self._ensure_pool()

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT id, process_id, parent_foe_id, created_at
                    FROM foes
                    WHERE process_id = :1
                    ORDER BY created_at
                    """,
                    [process_id],
                )
                rows = await cursor.fetchall()
                return [
                    FlowOfExecution(
                        id=row[0],
                        process_id=row[1],
                        parent_foe_id=row[2],
                        created_at=row[3],
                    )
                    for row in rows
                ]

    async def delete_foe(self, foe_id: str) -> bool:
        """Delete a flow of execution. Returns True if deleted."""
        pool = self._ensure_pool()

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("DELETE FROM foes WHERE id = :1", [foe_id])
                deleted = cursor.rowcount > 0
            await conn.commit()
            return deleted

    # =========================================================================
    # Locking Operations (Table-based, similar to SQLite)
    # =========================================================================

    async def acquire_lock(
        self, process_id: str, owner: str, timeout_seconds: float = 30.0
    ) -> bool:
        """Acquire a lock using Oracle with expiration-based timeout.

        Args:
            process_id: The process to lock
            owner: Identifier for the lock owner (e.g., engine instance ID)
            timeout_seconds: How long to wait for lock acquisition

        Returns:
            True if lock acquired, False if timeout
        """
        pool = self._ensure_pool()
        deadline = time.time() + timeout_seconds
        lock_duration = 60.0  # Lock expires after 60 seconds

        while time.time() < deadline:
            now = datetime.now(UTC)
            expires_at = datetime.fromtimestamp(time.time() + lock_duration, tz=UTC)

            try:
                async with pool.acquire() as conn:
                    async with conn.cursor() as cursor:
                        # Try to insert new lock or take over expired lock
                        await cursor.execute(
                            """
                            MERGE INTO process_locks l
                            USING (SELECT :1 AS process_id, :2 AS owner,
                                          :3 AS acquired_at, :4 AS expires_at FROM dual) s
                            ON (l.process_id = s.process_id)
                            WHEN MATCHED THEN
                                UPDATE SET owner = s.owner, acquired_at = s.acquired_at,
                                           expires_at = s.expires_at
                                WHERE l.owner = s.owner OR l.expires_at < :5
                            WHEN NOT MATCHED THEN
                                INSERT (process_id, owner, acquired_at, expires_at)
                                VALUES (s.process_id, s.owner, s.acquired_at, s.expires_at)
                            """,
                            [process_id, owner, now, expires_at, now],
                        )
                    await conn.commit()

                    # Check if we got the lock
                    async with conn.cursor() as cursor:
                        await cursor.execute(
                            "SELECT owner FROM process_locks WHERE process_id = :1",
                            [process_id],
                        )
                        row = await cursor.fetchone()
                        if row and row[0] == owner:
                            return True

            except oracledb.DatabaseError:
                pass

            # Wait before retrying
            await asyncio.sleep(0.1)

        return False

    async def release_lock(self, process_id: str, owner: str) -> bool:
        """Release a lock only if owned by the specified owner.

        Args:
            process_id: The process to unlock
            owner: Must match the owner that acquired the lock

        Returns:
            True if released, False if not locked or wrong owner
        """
        pool = self._ensure_pool()

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "DELETE FROM process_locks WHERE process_id = :1 AND owner = :2",
                    [process_id, owner],
                )
                released = cursor.rowcount > 0
            await conn.commit()
            return released

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
            try:
                yield
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise
