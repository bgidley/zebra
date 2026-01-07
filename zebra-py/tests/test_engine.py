"""Tests for the workflow engine."""

import pytest

from zebra.core.engine import WorkflowEngine
from zebra.core.models import (
    ProcessDefinition,
    ProcessState,
    RoutingDefinition,
    TaskDefinition,
    TaskInstance,
    TaskResult,
    TaskState,
)
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import ExecutionContext, TaskAction
from zebra.tasks.registry import ActionRegistry


class CountingAction(TaskAction):
    """A test action that counts executions."""

    execution_count = 0

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        CountingAction.execution_count += 1
        return TaskResult.ok(output={"count": CountingAction.execution_count})


class FailingAction(TaskAction):
    """A test action that always fails."""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        return TaskResult.fail("Intentional failure")


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture
def registry():
    reg = ActionRegistry()
    reg.register_action("counting", CountingAction)
    reg.register_action("failing", FailingAction)
    return reg


@pytest.fixture
def engine(store, registry):
    return WorkflowEngine(store, registry)


@pytest.fixture
def simple_definition():
    """A simple two-task sequential workflow."""
    return ProcessDefinition(
        id="simple",
        name="Simple Workflow",
        first_task_id="start",
        tasks={
            "start": TaskDefinition(id="start", name="Start", action="counting"),
            "end": TaskDefinition(id="end", name="End", action="counting"),
        },
        routings=[
            RoutingDefinition(id="r1", source_task_id="start", dest_task_id="end"),
        ],
    )


@pytest.fixture
def parallel_definition():
    """A workflow with parallel branches."""
    return ProcessDefinition(
        id="parallel",
        name="Parallel Workflow",
        first_task_id="start",
        tasks={
            "start": TaskDefinition(id="start", name="Start"),
            "branch_a": TaskDefinition(id="branch_a", name="Branch A", action="counting"),
            "branch_b": TaskDefinition(id="branch_b", name="Branch B", action="counting"),
            "join": TaskDefinition(
                id="join", name="Join", synchronized=True, action="counting"
            ),
        },
        routings=[
            RoutingDefinition(
                id="r1", source_task_id="start", dest_task_id="branch_a", parallel=True
            ),
            RoutingDefinition(
                id="r2", source_task_id="start", dest_task_id="branch_b", parallel=True
            ),
            RoutingDefinition(id="r3", source_task_id="branch_a", dest_task_id="join"),
            RoutingDefinition(id="r4", source_task_id="branch_b", dest_task_id="join"),
        ],
    )


class TestWorkflowEngine:
    @pytest.mark.asyncio
    async def test_create_process(self, engine, simple_definition):
        process = await engine.create_process(simple_definition)

        assert process.state == ProcessState.CREATED
        assert process.definition_id == simple_definition.id

        # Definition should be saved
        loaded = await engine.store.load_definition(simple_definition.id)
        assert loaded is not None

    @pytest.mark.asyncio
    async def test_start_process(self, engine, simple_definition):
        CountingAction.execution_count = 0

        process = await engine.create_process(simple_definition)
        process = await engine.start_process(process.id)

        assert process.state == ProcessState.COMPLETE
        # Both tasks should have run
        assert CountingAction.execution_count == 2

    @pytest.mark.asyncio
    async def test_process_with_properties(self, engine, simple_definition):
        process = await engine.create_process(
            simple_definition, properties={"key": "value"}
        )

        assert process.properties["key"] == "value"

    @pytest.mark.asyncio
    async def test_manual_task(self, engine, store, registry):
        """Test a workflow with a manual task."""
        definition = ProcessDefinition(
            id="manual",
            name="Manual Workflow",
            first_task_id="manual_task",
            tasks={
                "manual_task": TaskDefinition(
                    id="manual_task", name="Manual Task", auto=False
                ),
                "end": TaskDefinition(id="end", name="End"),
            },
            routings=[
                RoutingDefinition(
                    id="r1", source_task_id="manual_task", dest_task_id="end"
                ),
            ],
        )

        process = await engine.create_process(definition)
        await engine.start_process(process.id)

        # Process should be running, waiting for manual task
        process = await store.load_process(process.id)
        assert process.state == ProcessState.RUNNING

        # Get pending tasks
        pending = await engine.get_pending_tasks(process.id)
        assert len(pending) == 1
        assert pending[0].task_definition_id == "manual_task"

        # Complete the manual task
        await engine.complete_task(pending[0].id, TaskResult.ok(output="done"))

        # Process should be complete now
        process = await store.load_process(process.id)
        assert process.state == ProcessState.COMPLETE

    @pytest.mark.asyncio
    async def test_parallel_execution(self, engine, parallel_definition):
        """Test parallel branch execution with sync/join."""
        CountingAction.execution_count = 0

        process = await engine.create_process(parallel_definition)
        await engine.start_process(process.id)

        process = await engine.store.load_process(process.id)
        assert process.state == ProcessState.COMPLETE

        # Should have executed: branch_a, branch_b, join
        assert CountingAction.execution_count == 3

    @pytest.mark.asyncio
    async def test_pause_resume(self, engine, store, registry):
        """Test pausing and resuming a workflow."""
        definition = ProcessDefinition(
            id="pausable",
            name="Pausable",
            first_task_id="task1",
            tasks={
                "task1": TaskDefinition(id="task1", name="Task 1", auto=False),
                "task2": TaskDefinition(id="task2", name="Task 2"),
            },
            routings=[
                RoutingDefinition(id="r1", source_task_id="task1", dest_task_id="task2"),
            ],
        )

        process = await engine.create_process(definition)
        await engine.start_process(process.id)

        # Pause
        process = await engine.pause_process(process.id)
        assert process.state == ProcessState.PAUSED

        # Resume
        process = await engine.resume_process(process.id)
        assert process.state == ProcessState.RUNNING

    @pytest.mark.asyncio
    async def test_get_process_status(self, engine, store, registry):
        """Test getting detailed process status."""
        definition = ProcessDefinition(
            id="status_test",
            name="Status Test",
            first_task_id="task1",
            tasks={
                "task1": TaskDefinition(id="task1", name="Task 1", auto=False),
            },
        )

        process = await engine.create_process(definition)
        await engine.start_process(process.id)

        status = await engine.get_process_status(process.id)

        assert status["process"]["id"] == process.id
        assert status["process"]["definition"] == "Status Test"
        assert status["process"]["state"] == "running"
        assert len(status["tasks"]) == 1


class TestTaskSync:
    @pytest.mark.asyncio
    async def test_sync_task_waits_for_all_branches(self, engine, store, registry):
        """Test that sync tasks wait for all parallel branches."""
        definition = ProcessDefinition(
            id="sync_test",
            name="Sync Test",
            first_task_id="start",
            tasks={
                "start": TaskDefinition(id="start", name="Start"),
                "branch_a": TaskDefinition(
                    id="branch_a", name="Branch A", auto=False
                ),
                "branch_b": TaskDefinition(
                    id="branch_b", name="Branch B", auto=False
                ),
                "join": TaskDefinition(id="join", name="Join", synchronized=True),
            },
            routings=[
                RoutingDefinition(
                    id="r1", source_task_id="start", dest_task_id="branch_a", parallel=True
                ),
                RoutingDefinition(
                    id="r2", source_task_id="start", dest_task_id="branch_b", parallel=True
                ),
                RoutingDefinition(id="r3", source_task_id="branch_a", dest_task_id="join"),
                RoutingDefinition(id="r4", source_task_id="branch_b", dest_task_id="join"),
            ],
        )

        process = await engine.create_process(definition)
        await engine.start_process(process.id)

        # Should have two pending manual tasks
        pending = await engine.get_pending_tasks(process.id)
        task_ids = {t.task_definition_id for t in pending}
        assert task_ids == {"branch_a", "branch_b"}

        # Complete branch_a
        branch_a = next(t for t in pending if t.task_definition_id == "branch_a")
        await engine.complete_task(branch_a.id, TaskResult.ok())

        # Join should still be waiting (branch_b not done)
        process = await store.load_process(process.id)
        assert process.state == ProcessState.RUNNING

        # Complete branch_b
        pending = await engine.get_pending_tasks(process.id)
        branch_b = next(t for t in pending if t.task_definition_id == "branch_b")
        await engine.complete_task(branch_b.id, TaskResult.ok())

        # Now process should be complete
        process = await store.load_process(process.id)
        assert process.state == ProcessState.COMPLETE
