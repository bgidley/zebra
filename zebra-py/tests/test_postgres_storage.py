"""Tests for PostgreSQL storage backend."""

import os
from datetime import UTC, datetime

import pytest

from zebra.core.models import (
    FlowOfExecution,
    ProcessDefinition,
    ProcessInstance,
    ProcessState,
    RoutingDefinition,
    TaskDefinition,
    TaskInstance,
    TaskState,
)
from zebra.storage.postgres import PostgreSQLStore

# Skip all tests if PostgreSQL is not available
pytestmark = pytest.mark.skipif(
    os.environ.get("TEST_POSTGRES") != "1",
    reason="PostgreSQL tests disabled. Set TEST_POSTGRES=1 to enable.",
)


@pytest.fixture
async def postgres_store():
    """Create a PostgreSQL store for testing."""
    # Use Unix socket for peer authentication
    store = PostgreSQLStore(
        host="/var/run/postgresql",  # Unix socket path
        database="opc",
        user="opc",
    )
    await store.initialize()

    # Clean up any existing test data
    pool = store._ensure_pool()
    await pool.execute("DELETE FROM task_instances WHERE process_id LIKE 'test-%'")
    await pool.execute("DELETE FROM foes WHERE process_id LIKE 'test-%'")
    await pool.execute("DELETE FROM process_instances WHERE id LIKE 'test-%'")
    await pool.execute("DELETE FROM process_definitions WHERE id LIKE 'test-%'")

    yield store

    # Clean up after tests
    await pool.execute("DELETE FROM task_instances WHERE process_id LIKE 'test-%'")
    await pool.execute("DELETE FROM foes WHERE process_id LIKE 'test-%'")
    await pool.execute("DELETE FROM process_instances WHERE id LIKE 'test-%'")
    await pool.execute("DELETE FROM process_definitions WHERE id LIKE 'test-%'")

    await store.close()


@pytest.fixture
def sample_definition():
    """Create a sample process definition."""
    return ProcessDefinition(
        id="test-def-1",
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
        id="test-proc-1",
        definition_id="test-def-1",
        state=ProcessState.RUNNING,
        properties={"key": "value"},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


class TestPostgreSQLDefinitions:
    """Tests for process definition operations."""

    async def test_save_and_load_definition(self, postgres_store, sample_definition):
        """Test saving and loading a definition."""
        await postgres_store.save_definition(sample_definition)

        loaded = await postgres_store.load_definition(sample_definition.id)

        assert loaded is not None
        assert loaded.id == sample_definition.id
        assert loaded.name == sample_definition.name
        assert loaded.version == sample_definition.version
        assert len(loaded.tasks) == 2

    async def test_load_nonexistent_definition(self, postgres_store):
        """Test loading a definition that doesn't exist."""
        loaded = await postgres_store.load_definition("nonexistent")
        assert loaded is None

    async def test_list_definitions(self, postgres_store, sample_definition):
        """Test listing all definitions."""
        await postgres_store.save_definition(sample_definition)

        # Create another definition
        def2 = ProcessDefinition(
            id="test-def-2",
            name="Another Workflow",
            version=1,
            first_task_id="t1",
            tasks={"t1": TaskDefinition(id="t1", name="T1")},
            routings=[],
        )
        await postgres_store.save_definition(def2)

        definitions = await postgres_store.list_definitions()

        # Filter to only test definitions
        test_defs = [d for d in definitions if d.id.startswith("test-")]
        assert len(test_defs) >= 2

    async def test_update_definition(self, postgres_store, sample_definition):
        """Test updating an existing definition."""
        await postgres_store.save_definition(sample_definition)

        # Update the definition
        updated = ProcessDefinition(
            id=sample_definition.id,
            name="Updated Workflow",
            version=2,
            first_task_id="task1",
            tasks=sample_definition.tasks,
            routings=sample_definition.routings,
        )
        await postgres_store.save_definition(updated)

        loaded = await postgres_store.load_definition(sample_definition.id)
        assert loaded.name == "Updated Workflow"
        assert loaded.version == 2

    async def test_delete_definition(self, postgres_store, sample_definition):
        """Test deleting a definition."""
        await postgres_store.save_definition(sample_definition)

        result = await postgres_store.delete_definition(sample_definition.id)
        assert result is True

        loaded = await postgres_store.load_definition(sample_definition.id)
        assert loaded is None

    async def test_delete_nonexistent_definition(self, postgres_store):
        """Test deleting a definition that doesn't exist."""
        result = await postgres_store.delete_definition("nonexistent")
        assert result is False


class TestPostgreSQLProcesses:
    """Tests for process instance operations."""

    async def test_save_and_load_process(self, postgres_store, sample_definition, sample_process):
        """Test saving and loading a process."""
        await postgres_store.save_definition(sample_definition)
        await postgres_store.save_process(sample_process)

        loaded = await postgres_store.load_process(sample_process.id)

        assert loaded is not None
        assert loaded.id == sample_process.id
        assert loaded.definition_id == sample_process.definition_id
        assert loaded.state == ProcessState.RUNNING
        assert loaded.properties == {"key": "value"}

    async def test_load_nonexistent_process(self, postgres_store):
        """Test loading a process that doesn't exist."""
        loaded = await postgres_store.load_process("nonexistent")
        assert loaded is None

    async def test_list_processes(self, postgres_store, sample_definition, sample_process):
        """Test listing processes."""
        await postgres_store.save_definition(sample_definition)
        await postgres_store.save_process(sample_process)

        # Create a completed process
        completed = ProcessInstance(
            id="test-proc-2",
            definition_id="test-def-1",
            state=ProcessState.COMPLETE,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        await postgres_store.save_process(completed)

        # List only active processes
        active = await postgres_store.list_processes()
        active_test = [p for p in active if p.id.startswith("test-")]
        assert len(active_test) == 1
        assert active_test[0].id == "test-proc-1"

        # List all processes including completed
        all_procs = await postgres_store.list_processes(include_completed=True)
        all_test = [p for p in all_procs if p.id.startswith("test-")]
        assert len(all_test) >= 2

    async def test_list_processes_by_definition(
        self, postgres_store, sample_definition, sample_process
    ):
        """Test filtering processes by definition."""
        await postgres_store.save_definition(sample_definition)
        await postgres_store.save_process(sample_process)

        # Create another definition and process
        def2 = ProcessDefinition(
            id="test-def-other",
            name="Other",
            version=1,
            first_task_id="t1",
            tasks={"t1": TaskDefinition(id="t1", name="T1")},
            routings=[],
        )
        await postgres_store.save_definition(def2)

        other = ProcessInstance(
            id="test-proc-other",
            definition_id="test-def-other",
            state=ProcessState.RUNNING,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        await postgres_store.save_process(other)

        filtered = await postgres_store.list_processes(definition_id="test-def-1")
        test_filtered = [p for p in filtered if p.id.startswith("test-")]
        assert len(test_filtered) == 1
        assert test_filtered[0].definition_id == "test-def-1"

    async def test_update_process(self, postgres_store, sample_definition, sample_process):
        """Test updating a process."""
        await postgres_store.save_definition(sample_definition)
        await postgres_store.save_process(sample_process)

        sample_process.state = ProcessState.COMPLETE
        sample_process.properties["new_key"] = "new_value"
        await postgres_store.save_process(sample_process)

        loaded = await postgres_store.load_process(sample_process.id)
        assert loaded.state == ProcessState.COMPLETE
        assert loaded.properties["new_key"] == "new_value"

    async def test_delete_process_cascades(self, postgres_store, sample_definition, sample_process):
        """Test that deleting a process cascades to tasks and FOEs."""
        await postgres_store.save_definition(sample_definition)
        await postgres_store.save_process(sample_process)

        # Create a task for the process
        task = TaskInstance(
            id="test-task-1",
            process_id=sample_process.id,
            task_definition_id="task1",
            state=TaskState.READY,
            foe_id="test-foe-1",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        await postgres_store.save_task(task)

        # Create a FOE for the process
        foe = FlowOfExecution(
            id="test-foe-1",
            process_id=sample_process.id,
            created_at=datetime.now(UTC),
        )
        await postgres_store.save_foe(foe)

        # Delete the process
        result = await postgres_store.delete_process(sample_process.id)
        assert result is True

        # Verify cascade deletes
        assert await postgres_store.load_process(sample_process.id) is None
        assert await postgres_store.load_task(task.id) is None
        assert await postgres_store.load_foe(foe.id) is None


class TestPostgreSQLTasks:
    """Tests for task instance operations."""

    async def test_save_and_load_task(self, postgres_store, sample_definition, sample_process):
        """Test saving and loading a task."""
        await postgres_store.save_definition(sample_definition)
        await postgres_store.save_process(sample_process)

        task = TaskInstance(
            id="test-task-1",
            process_id=sample_process.id,
            task_definition_id="task1",
            state=TaskState.READY,
            foe_id="test-foe-1",
            properties={"task_key": "task_value"},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        await postgres_store.save_task(task)

        loaded = await postgres_store.load_task(task.id)
        assert loaded is not None
        assert loaded.id == task.id
        assert loaded.state == TaskState.READY
        assert loaded.properties == {"task_key": "task_value"}

    async def test_load_tasks_for_process(self, postgres_store, sample_definition, sample_process):
        """Test loading all tasks for a process."""
        await postgres_store.save_definition(sample_definition)
        await postgres_store.save_process(sample_process)

        # Create multiple tasks
        for i in range(3):
            task = TaskInstance(
                id=f"test-task-{i}",
                process_id=sample_process.id,
                task_definition_id=f"task{i}",
                state=TaskState.READY,
                foe_id="test-foe-1",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            await postgres_store.save_task(task)

        tasks = await postgres_store.load_tasks_for_process(sample_process.id)
        assert len(tasks) == 3


class TestPostgreSQLFOEs:
    """Tests for Flow of Execution operations."""

    async def test_save_and_load_foe(self, postgres_store, sample_definition, sample_process):
        """Test saving and loading a FOE."""
        await postgres_store.save_definition(sample_definition)
        await postgres_store.save_process(sample_process)

        foe = FlowOfExecution(
            id="test-foe-1",
            process_id=sample_process.id,
            created_at=datetime.now(UTC),
        )
        await postgres_store.save_foe(foe)

        loaded = await postgres_store.load_foe(foe.id)
        assert loaded is not None
        assert loaded.id == foe.id
        assert loaded.process_id == sample_process.id

    async def test_load_foes_for_process(self, postgres_store, sample_definition, sample_process):
        """Test loading all FOEs for a process."""
        await postgres_store.save_definition(sample_definition)
        await postgres_store.save_process(sample_process)

        # Create multiple FOEs (parent-child relationship)
        parent_foe = FlowOfExecution(
            id="test-foe-parent",
            process_id=sample_process.id,
            created_at=datetime.now(UTC),
        )
        await postgres_store.save_foe(parent_foe)

        child_foe = FlowOfExecution(
            id="test-foe-child",
            process_id=sample_process.id,
            parent_foe_id=parent_foe.id,
            created_at=datetime.now(UTC),
        )
        await postgres_store.save_foe(child_foe)

        foes = await postgres_store.load_foes_for_process(sample_process.id)
        assert len(foes) == 2


class TestPostgreSQLLocking:
    """Tests for advisory lock operations."""

    async def test_acquire_lock(self, postgres_store, sample_definition, sample_process):
        """Test acquiring a lock."""
        await postgres_store.save_definition(sample_definition)
        await postgres_store.save_process(sample_process)

        # Acquire lock
        acquired = await postgres_store.acquire_lock(sample_process.id, "owner1", timeout_seconds=5)
        assert acquired is True

    async def test_lock_context_manager(self, postgres_store, sample_definition, sample_process):
        """Test using the lock context manager."""
        await postgres_store.save_definition(sample_definition)
        await postgres_store.save_process(sample_process)

        async with postgres_store.lock(sample_process.id, "owner1") as acquired:
            assert acquired is True
            # Do work with process

        # Lock should be automatically released


class TestPostgreSQLTransactions:
    """Tests for transaction support."""

    async def test_transaction_commit(self, postgres_store, sample_definition):
        """Test that transactions commit correctly."""
        async with postgres_store.transaction():
            await postgres_store.save_definition(sample_definition)

        # Should be visible after transaction
        loaded = await postgres_store.load_definition(sample_definition.id)
        assert loaded is not None
