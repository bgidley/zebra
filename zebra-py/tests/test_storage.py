"""Tests for storage implementations."""

import pytest
from datetime import datetime

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
from zebra.storage.memory import InMemoryStore


@pytest.fixture
def store():
    """Create a fresh in-memory store for each test."""
    return InMemoryStore()


@pytest.fixture
def sample_definition():
    """Create a sample process definition."""
    return ProcessDefinition(
        id="def1",
        name="Test Process",
        first_task_id="start",
        tasks={
            "start": TaskDefinition(id="start", name="Start Task"),
            "end": TaskDefinition(id="end", name="End Task"),
        },
        routings=[
            RoutingDefinition(id="r1", source_task_id="start", dest_task_id="end"),
        ],
    )


@pytest.fixture
def sample_process():
    """Create a sample process instance."""
    return ProcessInstance(
        id="proc1",
        definition_id="def1",
        state=ProcessState.RUNNING,
        properties={"test_key": "test_value"},
    )


@pytest.fixture
def sample_task():
    """Create a sample task instance."""
    return TaskInstance(
        id="task1",
        process_id="proc1",
        task_definition_id="start",
        state=TaskState.READY,
        foe_id="foe1",
    )


class TestInMemoryStore:
    @pytest.mark.asyncio
    async def test_save_and_load_definition(self, store, sample_definition):
        await store.save_definition(sample_definition)
        loaded = await store.load_definition("def1")

        assert loaded is not None
        assert loaded.id == "def1"
        assert loaded.name == "Test Process"
        assert len(loaded.tasks) == 2

    @pytest.mark.asyncio
    async def test_load_nonexistent_definition(self, store):
        loaded = await store.load_definition("nonexistent")
        assert loaded is None

    @pytest.mark.asyncio
    async def test_list_definitions(self, store, sample_definition):
        await store.save_definition(sample_definition)

        definitions = await store.list_definitions()
        assert len(definitions) == 1
        assert definitions[0].id == "def1"

    @pytest.mark.asyncio
    async def test_delete_definition(self, store, sample_definition):
        await store.save_definition(sample_definition)

        deleted = await store.delete_definition("def1")
        assert deleted is True

        deleted_again = await store.delete_definition("def1")
        assert deleted_again is False

        loaded = await store.load_definition("def1")
        assert loaded is None

    @pytest.mark.asyncio
    async def test_save_and_load_process(self, store, sample_process):
        await store.save_process(sample_process)
        loaded = await store.load_process("proc1")

        assert loaded is not None
        assert loaded.id == "proc1"
        assert loaded.state == ProcessState.RUNNING
        assert loaded.properties["test_key"] == "test_value"

    @pytest.mark.asyncio
    async def test_list_processes(self, store, sample_process):
        await store.save_process(sample_process)

        # Create a completed process
        completed = ProcessInstance(
            id="proc2",
            definition_id="def1",
            state=ProcessState.COMPLETE,
        )
        await store.save_process(completed)

        # List active only
        active = await store.list_processes(include_completed=False)
        assert len(active) == 1
        assert active[0].id == "proc1"

        # List all
        all_procs = await store.list_processes(include_completed=True)
        assert len(all_procs) == 2

    @pytest.mark.asyncio
    async def test_save_and_load_task(self, store, sample_task):
        await store.save_task(sample_task)
        loaded = await store.load_task("task1")

        assert loaded is not None
        assert loaded.id == "task1"
        assert loaded.state == TaskState.READY

    @pytest.mark.asyncio
    async def test_load_tasks_for_process(self, store, sample_task):
        await store.save_task(sample_task)

        task2 = TaskInstance(
            id="task2",
            process_id="proc1",
            task_definition_id="end",
            state=TaskState.PENDING,
            foe_id="foe1",
        )
        await store.save_task(task2)

        # Task for different process
        task3 = TaskInstance(
            id="task3",
            process_id="proc2",
            task_definition_id="start",
            state=TaskState.READY,
            foe_id="foe2",
        )
        await store.save_task(task3)

        tasks = await store.load_tasks_for_process("proc1")
        assert len(tasks) == 2
        assert all(t.process_id == "proc1" for t in tasks)

    @pytest.mark.asyncio
    async def test_foe_operations(self, store):
        foe = FlowOfExecution(
            id="foe1",
            process_id="proc1",
            parent_foe_id=None,
        )
        await store.save_foe(foe)

        loaded = await store.load_foe("foe1")
        assert loaded is not None
        assert loaded.id == "foe1"

        foes = await store.load_foes_for_process("proc1")
        assert len(foes) == 1

    @pytest.mark.asyncio
    async def test_locking(self, store):
        # Acquire lock
        acquired = await store.acquire_lock("proc1", "owner1", timeout_seconds=1.0)
        assert acquired is True

        # Same owner can acquire again
        acquired_again = await store.acquire_lock("proc1", "owner1", timeout_seconds=1.0)
        assert acquired_again is True

        # Release lock
        released = await store.release_lock("proc1", "owner1")
        assert released is True

        # Can't release if not owner
        released_wrong = await store.release_lock("proc1", "owner2")
        assert released_wrong is False

    @pytest.mark.asyncio
    async def test_lock_context_manager(self, store):
        async with store.lock("proc1", "owner1") as acquired:
            assert acquired is True

            # Lock should be held
            assert "proc1" in store._locks

        # Lock should be released
        assert "proc1" not in store._locks

    @pytest.mark.asyncio
    async def test_delete_process_cascades(self, store, sample_process, sample_task):
        await store.save_process(sample_process)
        await store.save_task(sample_task)

        foe = FlowOfExecution(id="foe1", process_id="proc1")
        await store.save_foe(foe)

        # Delete process
        deleted = await store.delete_process("proc1")
        assert deleted is True

        # Related data should be gone
        assert await store.load_process("proc1") is None
        assert await store.load_task("task1") is None
        assert await store.load_foe("foe1") is None

    def test_clear(self, store):
        store._definitions["def1"] = None
        store._processes["proc1"] = None

        store.clear()

        assert len(store._definitions) == 0
        assert len(store._processes) == 0

    @pytest.mark.asyncio
    async def test_get_running_processes(self, store, sample_definition):
        """Test get_running_processes returns only RUNNING processes."""
        # Create processes in different states
        process1 = ProcessInstance(
            id="proc1",
            definition_id="def1",
            state=ProcessState.RUNNING,
            properties={},
        )
        process2 = ProcessInstance(
            id="proc2",
            definition_id="def1",
            state=ProcessState.PAUSED,
            properties={},
        )
        process3 = ProcessInstance(
            id="proc3",
            definition_id="def1",
            state=ProcessState.COMPLETE,
            properties={},
        )
        process4 = ProcessInstance(
            id="proc4",
            definition_id="def1",
            state=ProcessState.RUNNING,
            properties={},
        )

        await store.save_definition(sample_definition)
        await store.save_process(process1)
        await store.save_process(process2)
        await store.save_process(process3)
        await store.save_process(process4)

        # Should return only RUNNING processes
        running = await store.get_running_processes()
        assert len(running) == 2
        assert {p.id for p in running} == {"proc1", "proc4"}

        for proc in running:
            assert proc.state == ProcessState.RUNNING

    @pytest.mark.asyncio
    async def test_get_running_processes_empty(self, store):
        """Test get_running_processes returns empty list when no running processes."""
        running = await store.get_running_processes()
        assert len(running) == 0
        assert isinstance(running, list)

    @pytest.mark.asyncio
    async def test_get_running_tasks(self, store, sample_definition, sample_process):
        """Test get_running_tasks returns only RUNNING tasks."""
        # Save definition and process
        await store.save_definition(sample_definition)
        await store.save_process(sample_process)

        # Create tasks in different states
        task1 = TaskInstance(
            id="task1",
            process_id="proc1",
            task_definition_id="start",
            state=TaskState.RUNNING,
            foe_id="foe1",
            properties={},
        )
        task2 = TaskInstance(
            id="task2",
            process_id="proc1",
            task_definition_id="start",
            state=TaskState.READY,
            foe_id="foe1",
            properties={},
        )
        task3 = TaskInstance(
            id="task3",
            process_id="proc1",
            task_definition_id="start",
            state=TaskState.RUNNING,
            foe_id="foe1",
            properties={},
        )
        task4 = TaskInstance(
            id="task4",
            process_id="proc1",
            task_definition_id="start",
            state=TaskState.COMPLETE,
            foe_id="foe1",
            properties={},
        )

        await store.save_task(task1)
        await store.save_task(task2)
        await store.save_task(task3)
        await store.save_task(task4)

        # Get all running tasks
        running = await store.get_running_tasks()
        assert len(running) == 2
        task_ids = {t.id for t in running}
        assert task_ids == {"task1", "task3"}

        for task in running:
            assert task.state == TaskState.RUNNING

        # Get running tasks for specific process
        running_proc = await store.get_running_tasks(process_id="proc1")
        assert len(running_proc) == 2
        assert {t.id for t in running_proc} == {"task1", "task3"}

        # Get running tasks for non-existent process
        running_empty = await store.get_running_tasks(process_id="nonexistent")
        assert len(running_empty) == 0
