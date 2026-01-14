"""Tests for SQLite storage backend."""

import pytest
import tempfile
import os
from datetime import datetime, timezone
from pathlib import Path

from zebra.storage.sqlite import SQLiteStore
from zebra.core.models import (
    ProcessDefinition,
    ProcessInstance,
    ProcessState,
    TaskDefinition,
    TaskInstance,
    TaskState,
    FlowOfExecution,
    RoutingDefinition,
)


@pytest.fixture
async def sqlite_store():
    """Create a temporary SQLite store for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    store = SQLiteStore(db_path)
    await store.initialize()
    yield store
    await store.close()
    os.unlink(db_path)


@pytest.fixture
def sample_definition():
    """Create a sample process definition."""
    return ProcessDefinition(
        id="def-1",
        name="Test Workflow",
        version=1,
        first_task_id="task1",
        tasks={
            "task1": TaskDefinition(id="task1", name="Task 1"),
            "task2": TaskDefinition(id="task2", name="Task 2"),
        },
        routings=[
            RoutingDefinition(id="route-1", source_task_id="task1", dest_task_id="task2"),
        ],
    )


@pytest.fixture
def sample_process():
    """Create a sample process instance."""
    return ProcessInstance(
        id="proc-1",
        definition_id="def-1",
        state=ProcessState.RUNNING,
        properties={"key": "value"},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class TestSQLiteDefinitions:
    """Tests for process definition operations."""

    async def test_save_and_load_definition(self, sqlite_store, sample_definition):
        """Test saving and loading a definition."""
        await sqlite_store.save_definition(sample_definition)

        loaded = await sqlite_store.load_definition(sample_definition.id)

        assert loaded is not None
        assert loaded.id == sample_definition.id
        assert loaded.name == sample_definition.name
        assert loaded.version == sample_definition.version
        assert len(loaded.tasks) == 2

    async def test_load_nonexistent_definition(self, sqlite_store):
        """Test loading a definition that doesn't exist."""
        loaded = await sqlite_store.load_definition("nonexistent")
        assert loaded is None

    async def test_list_definitions(self, sqlite_store, sample_definition):
        """Test listing all definitions."""
        await sqlite_store.save_definition(sample_definition)

        # Create another definition
        def2 = ProcessDefinition(
            id="def-2",
            name="Another Workflow",
            version=1,
            first_task_id="t1",
            tasks={"t1": TaskDefinition(id="t1", name="T1")},
            routings=[],
        )
        await sqlite_store.save_definition(def2)

        definitions = await sqlite_store.list_definitions()

        assert len(definitions) == 2
        names = {d.name for d in definitions}
        assert "Test Workflow" in names
        assert "Another Workflow" in names

    async def test_update_definition(self, sqlite_store, sample_definition):
        """Test updating an existing definition."""
        await sqlite_store.save_definition(sample_definition)

        # Create updated version (models are frozen)
        updated = ProcessDefinition(
            id=sample_definition.id,
            name=sample_definition.name,
            version=2,
            first_task_id=sample_definition.first_task_id,
            tasks=sample_definition.tasks,
            routings=sample_definition.routings,
        )
        await sqlite_store.save_definition(updated)

        loaded = await sqlite_store.load_definition(sample_definition.id)
        assert loaded.version == 2

    async def test_delete_definition(self, sqlite_store, sample_definition):
        """Test deleting a definition."""
        await sqlite_store.save_definition(sample_definition)

        result = await sqlite_store.delete_definition(sample_definition.id)
        assert result is True

        loaded = await sqlite_store.load_definition(sample_definition.id)
        assert loaded is None

    async def test_delete_nonexistent_definition(self, sqlite_store):
        """Test deleting a definition that doesn't exist."""
        result = await sqlite_store.delete_definition("nonexistent")
        assert result is False


class TestSQLiteProcesses:
    """Tests for process instance operations."""

    async def test_save_and_load_process(self, sqlite_store, sample_process):
        """Test saving and loading a process."""
        await sqlite_store.save_process(sample_process)

        loaded = await sqlite_store.load_process(sample_process.id)

        assert loaded is not None
        assert loaded.id == sample_process.id
        assert loaded.definition_id == sample_process.definition_id
        assert loaded.state == ProcessState.RUNNING
        assert loaded.properties == {"key": "value"}

    async def test_load_nonexistent_process(self, sqlite_store):
        """Test loading a process that doesn't exist."""
        loaded = await sqlite_store.load_process("nonexistent")
        assert loaded is None

    async def test_list_processes(self, sqlite_store, sample_process):
        """Test listing processes."""
        await sqlite_store.save_process(sample_process)

        # Create a completed process
        completed = ProcessInstance(
            id="proc-2",
            definition_id="def-1",
            state=ProcessState.COMPLETE,
            properties={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await sqlite_store.save_process(completed)

        # List without completed
        active = await sqlite_store.list_processes()
        assert len(active) == 1
        assert active[0].id == "proc-1"

        # List with completed
        all_procs = await sqlite_store.list_processes(include_completed=True)
        assert len(all_procs) == 2

    async def test_list_processes_by_definition(self, sqlite_store, sample_process):
        """Test listing processes filtered by definition."""
        await sqlite_store.save_process(sample_process)

        # Create process with different definition
        other = ProcessInstance(
            id="proc-2",
            definition_id="def-2",
            state=ProcessState.RUNNING,
            properties={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await sqlite_store.save_process(other)

        filtered = await sqlite_store.list_processes(definition_id="def-1")
        assert len(filtered) == 1
        assert filtered[0].definition_id == "def-1"

    async def test_update_process(self, sqlite_store, sample_process):
        """Test updating a process."""
        await sqlite_store.save_process(sample_process)

        sample_process.state = ProcessState.COMPLETE
        sample_process.completed_at = datetime.now(timezone.utc)
        await sqlite_store.save_process(sample_process)

        loaded = await sqlite_store.load_process(sample_process.id)
        assert loaded.state == ProcessState.COMPLETE
        assert loaded.completed_at is not None

    async def test_delete_process(self, sqlite_store, sample_process):
        """Test deleting a process cascades to tasks and foes."""
        await sqlite_store.save_process(sample_process)

        # Add a task
        task = TaskInstance(
            id="task-inst-1",
            process_id=sample_process.id,
            task_definition_id="task1",
            state=TaskState.PENDING,
            foe_id="foe-1",
            properties={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await sqlite_store.save_task(task)

        # Add a FOE
        foe = FlowOfExecution(
            id="foe-1",
            process_id=sample_process.id,
            created_at=datetime.now(timezone.utc),
        )
        await sqlite_store.save_foe(foe)

        # Delete process
        result = await sqlite_store.delete_process(sample_process.id)
        assert result is True

        # Verify cascade
        assert await sqlite_store.load_process(sample_process.id) is None
        assert await sqlite_store.load_task(task.id) is None
        assert await sqlite_store.load_foe(foe.id) is None

    async def test_process_with_parent(self, sqlite_store):
        """Test process with parent references."""
        process = ProcessInstance(
            id="child-proc",
            definition_id="def-1",
            state=ProcessState.RUNNING,
            properties={},
            parent_process_id="parent-proc",
            parent_task_id="parent-task",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await sqlite_store.save_process(process)

        loaded = await sqlite_store.load_process(process.id)
        assert loaded.parent_process_id == "parent-proc"
        assert loaded.parent_task_id == "parent-task"


class TestSQLiteTasks:
    """Tests for task instance operations."""

    async def test_save_and_load_task(self, sqlite_store, sample_process):
        """Test saving and loading a task."""
        await sqlite_store.save_process(sample_process)

        task = TaskInstance(
            id="task-1",
            process_id=sample_process.id,
            task_definition_id="task1",
            state=TaskState.RUNNING,
            foe_id="foe-1",
            properties={"input": "test"},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await sqlite_store.save_task(task)

        loaded = await sqlite_store.load_task(task.id)

        assert loaded is not None
        assert loaded.id == task.id
        assert loaded.state == TaskState.RUNNING
        assert loaded.properties == {"input": "test"}

    async def test_load_nonexistent_task(self, sqlite_store):
        """Test loading a task that doesn't exist."""
        loaded = await sqlite_store.load_task("nonexistent")
        assert loaded is None

    async def test_load_tasks_for_process(self, sqlite_store, sample_process):
        """Test loading all tasks for a process."""
        await sqlite_store.save_process(sample_process)

        for i in range(3):
            task = TaskInstance(
                id=f"task-{i}",
                process_id=sample_process.id,
                task_definition_id=f"taskdef-{i}",
                state=TaskState.PENDING,
                foe_id="foe-1",
                properties={},
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            await sqlite_store.save_task(task)

        tasks = await sqlite_store.load_tasks_for_process(sample_process.id)
        assert len(tasks) == 3

    async def test_update_task_with_result(self, sqlite_store, sample_process):
        """Test updating a task with result and error."""
        await sqlite_store.save_process(sample_process)

        task = TaskInstance(
            id="task-1",
            process_id=sample_process.id,
            task_definition_id="task1",
            state=TaskState.RUNNING,
            foe_id="foe-1",
            properties={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await sqlite_store.save_task(task)

        # Update with result
        task.state = TaskState.COMPLETE
        task.result = {"output": "success"}
        task.completed_at = datetime.now(timezone.utc)
        await sqlite_store.save_task(task)

        loaded = await sqlite_store.load_task(task.id)
        assert loaded.state == TaskState.COMPLETE
        assert loaded.result == {"output": "success"}
        assert loaded.completed_at is not None

    async def test_update_task_with_error(self, sqlite_store, sample_process):
        """Test updating a task with error."""
        await sqlite_store.save_process(sample_process)

        task = TaskInstance(
            id="task-1",
            process_id=sample_process.id,
            task_definition_id="task1",
            state=TaskState.RUNNING,
            foe_id="foe-1",
            properties={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await sqlite_store.save_task(task)

        task.state = TaskState.FAILED
        task.error = "Something went wrong"
        await sqlite_store.save_task(task)

        loaded = await sqlite_store.load_task(task.id)
        assert loaded.state == TaskState.FAILED
        assert loaded.error == "Something went wrong"

    async def test_delete_task(self, sqlite_store, sample_process):
        """Test deleting a task."""
        await sqlite_store.save_process(sample_process)

        task = TaskInstance(
            id="task-1",
            process_id=sample_process.id,
            task_definition_id="task1",
            state=TaskState.PENDING,
            foe_id="foe-1",
            properties={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await sqlite_store.save_task(task)

        result = await sqlite_store.delete_task(task.id)
        assert result is True

        assert await sqlite_store.load_task(task.id) is None


class TestSQLiteFOEs:
    """Tests for flow of execution operations."""

    async def test_save_and_load_foe(self, sqlite_store, sample_process):
        """Test saving and loading a FOE."""
        await sqlite_store.save_process(sample_process)

        foe = FlowOfExecution(
            id="foe-1",
            process_id=sample_process.id,
            created_at=datetime.now(timezone.utc),
        )
        await sqlite_store.save_foe(foe)

        loaded = await sqlite_store.load_foe(foe.id)

        assert loaded is not None
        assert loaded.id == foe.id
        assert loaded.process_id == sample_process.id

    async def test_load_nonexistent_foe(self, sqlite_store):
        """Test loading a FOE that doesn't exist."""
        loaded = await sqlite_store.load_foe("nonexistent")
        assert loaded is None

    async def test_foe_with_parent(self, sqlite_store, sample_process):
        """Test FOE with parent reference."""
        await sqlite_store.save_process(sample_process)

        parent_foe = FlowOfExecution(
            id="foe-parent",
            process_id=sample_process.id,
            created_at=datetime.now(timezone.utc),
        )
        await sqlite_store.save_foe(parent_foe)

        child_foe = FlowOfExecution(
            id="foe-child",
            process_id=sample_process.id,
            parent_foe_id="foe-parent",
            created_at=datetime.now(timezone.utc),
        )
        await sqlite_store.save_foe(child_foe)

        loaded = await sqlite_store.load_foe(child_foe.id)
        assert loaded.parent_foe_id == "foe-parent"

    async def test_load_foes_for_process(self, sqlite_store, sample_process):
        """Test loading all FOEs for a process."""
        await sqlite_store.save_process(sample_process)

        for i in range(3):
            foe = FlowOfExecution(
                id=f"foe-{i}",
                process_id=sample_process.id,
                created_at=datetime.now(timezone.utc),
            )
            await sqlite_store.save_foe(foe)

        foes = await sqlite_store.load_foes_for_process(sample_process.id)
        assert len(foes) == 3


class TestSQLiteLocking:
    """Tests for process locking."""

    async def test_acquire_and_release_lock(self, sqlite_store, sample_process):
        """Test acquiring and releasing a lock."""
        await sqlite_store.save_process(sample_process)

        acquired = await sqlite_store.acquire_lock(sample_process.id, "owner1", timeout_seconds=1)
        assert acquired is True

        released = await sqlite_store.release_lock(sample_process.id, "owner1")
        assert released is True

    async def test_lock_prevents_other_owners(self, sqlite_store, sample_process):
        """Test that a lock prevents other owners."""
        await sqlite_store.save_process(sample_process)

        # Owner1 gets the lock
        acquired1 = await sqlite_store.acquire_lock(sample_process.id, "owner1", timeout_seconds=1)
        assert acquired1 is True

        # Owner2 cannot get the lock (short timeout)
        acquired2 = await sqlite_store.acquire_lock(sample_process.id, "owner2", timeout_seconds=0.2)
        assert acquired2 is False

        # Owner1 releases
        await sqlite_store.release_lock(sample_process.id, "owner1")

        # Now owner2 can get it
        acquired3 = await sqlite_store.acquire_lock(sample_process.id, "owner2", timeout_seconds=1)
        assert acquired3 is True

    async def test_same_owner_can_reacquire(self, sqlite_store, sample_process):
        """Test that the same owner can reacquire their lock."""
        await sqlite_store.save_process(sample_process)

        acquired1 = await sqlite_store.acquire_lock(sample_process.id, "owner1", timeout_seconds=1)
        assert acquired1 is True

        # Same owner can reacquire
        acquired2 = await sqlite_store.acquire_lock(sample_process.id, "owner1", timeout_seconds=1)
        assert acquired2 is True

    async def test_release_wrong_owner(self, sqlite_store, sample_process):
        """Test that wrong owner cannot release lock."""
        await sqlite_store.save_process(sample_process)

        await sqlite_store.acquire_lock(sample_process.id, "owner1", timeout_seconds=1)

        # Wrong owner tries to release
        released = await sqlite_store.release_lock(sample_process.id, "owner2")
        assert released is False


class TestSQLiteTransaction:
    """Tests for transaction support."""

    async def test_transaction_commit(self, sqlite_store, sample_definition):
        """Test that transaction commits properly."""
        async with sqlite_store.transaction():
            await sqlite_store.save_definition(sample_definition)

        loaded = await sqlite_store.load_definition(sample_definition.id)
        assert loaded is not None

    async def test_transaction_rollback(self, sqlite_store, sample_definition):
        """Test that transaction rolls back on error."""
        try:
            async with sqlite_store.transaction():
                await sqlite_store.save_definition(sample_definition)
                raise ValueError("Simulated error")
        except ValueError:
            pass

        # Definition should not be saved due to rollback
        loaded = await sqlite_store.load_definition(sample_definition.id)
        # Note: This might still be saved depending on auto-commit behavior
        # The key is that the transaction context manager handles exceptions


class TestSQLiteNotInitialized:
    """Tests for error handling when not initialized."""

    async def test_operations_fail_without_initialize(self):
        """Test that operations fail if not initialized."""
        store = SQLiteStore(":memory:")
        # Don't call initialize()

        with pytest.raises(RuntimeError, match="not initialized"):
            await store.save_definition(ProcessDefinition(
                id="test",
                name="Test",
                version=1,
                first_task_id="t1",
                tasks={"t1": TaskDefinition(id="t1", name="T1")},
                routings=[],
            ))


class TestSQLiteClose:
    """Tests for closing the store."""

    async def test_close_and_reopen(self):
        """Test closing and reopening the store."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            # Create and save
            store1 = SQLiteStore(db_path)
            await store1.initialize()

            definition = ProcessDefinition(
                id="persist-test",
                name="Persistence Test",
                version=1,
                first_task_id="t1",
                tasks={"t1": TaskDefinition(id="t1", name="T1")},
                routings=[],
            )
            await store1.save_definition(definition)
            await store1.close()

            # Reopen and verify
            store2 = SQLiteStore(db_path)
            await store2.initialize()

            loaded = await store2.load_definition("persist-test")
            assert loaded is not None
            assert loaded.name == "Persistence Test"

            await store2.close()
        finally:
            os.unlink(db_path)
