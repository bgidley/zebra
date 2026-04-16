"""Tests for the workflow engine."""

import pytest

from zebra.core.engine import WorkflowEngine
from zebra.core.exceptions import InvalidStateTransitionError, ProcessNotFoundError
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
            "join": TaskDefinition(id="join", name="Join", synchronized=True, action="counting"),
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
        process = await engine.create_process(simple_definition, properties={"key": "value"})

        assert process.properties["key"] == "value"

    @pytest.mark.asyncio
    async def test_manual_task(self, engine, store, registry):
        """Test a workflow with a manual task."""
        definition = ProcessDefinition(
            id="manual",
            name="Manual Workflow",
            first_task_id="manual_task",
            tasks={
                "manual_task": TaskDefinition(id="manual_task", name="Manual Task", auto=False),
                "end": TaskDefinition(id="end", name="End"),
            },
            routings=[
                RoutingDefinition(id="r1", source_task_id="manual_task", dest_task_id="end"),
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


class TestConventionBasedHumanTask:
    """Test the convention-based auto:false pattern for human tasks.

    Human tasks use auto:false with form schema in task properties.
    External callers read task properties to render UI, then call
    engine.complete_task() with user data to resume the workflow.
    """

    @pytest.mark.asyncio
    async def test_human_task_with_form_schema(self, engine, store):
        """Test full lifecycle: task properties as form schema, external completion,
        and result accessible to downstream tasks."""
        definition = ProcessDefinition(
            id="human_task_test",
            name="Human Task Test",
            first_task_id="get_input",
            tasks={
                "get_input": TaskDefinition(
                    id="get_input",
                    name="Get User Input",
                    auto=False,
                    properties={
                        "type": "text_input",
                        "prompt": "Enter your name",
                        "required": True,
                    },
                ),
                "process_input": TaskDefinition(
                    id="process_input",
                    name="Process Input",
                    action="counting",
                ),
            },
            routings=[
                RoutingDefinition(
                    id="r1", source_task_id="get_input", dest_task_id="process_input"
                ),
            ],
        )

        CountingAction.execution_count = 0

        # Create and start process
        process = await engine.create_process(definition)
        await engine.start_process(process.id)

        # Process should be running, waiting for the manual task
        process = await store.load_process(process.id)
        assert process.state == ProcessState.RUNNING

        # Get pending tasks - should find our human task
        pending = await engine.get_pending_tasks(process.id)
        assert len(pending) == 1
        task = pending[0]
        assert task.task_definition_id == "get_input"
        assert task.state == TaskState.READY

        # External caller reads task definition properties (form schema)
        task_def = definition.tasks["get_input"]
        assert task_def.properties["type"] == "text_input"
        assert task_def.properties["prompt"] == "Enter your name"
        assert task_def.properties["required"] is True

        # External caller completes task with user data
        user_response = "Alice"
        await engine.complete_task(task.id, TaskResult.ok(output=user_response))

        # Result should be stored in process properties
        process = await store.load_process(process.id)
        assert process.properties["__task_output_get_input"] == "Alice"

        # Downstream task should have executed
        assert CountingAction.execution_count == 1

        # Process should be complete
        assert process.state == ProcessState.COMPLETE

    @pytest.mark.asyncio
    async def test_human_task_with_structured_output(self, engine, store):
        """Test human task with structured (dict) output from the user."""
        definition = ProcessDefinition(
            id="structured_test",
            name="Structured Human Task",
            first_task_id="form_task",
            tasks={
                "form_task": TaskDefinition(
                    id="form_task",
                    name="Fill Form",
                    auto=False,
                    properties={
                        "type": "form",
                        "fields": [
                            {"name": "first_name", "label": "First Name", "required": True},
                            {"name": "email", "label": "Email", "required": True},
                        ],
                    },
                ),
                "done": TaskDefinition(id="done", name="Done"),
            },
            routings=[
                RoutingDefinition(id="r1", source_task_id="form_task", dest_task_id="done"),
            ],
        )

        process = await engine.create_process(definition)
        await engine.start_process(process.id)

        pending = await engine.get_pending_tasks(process.id)
        assert len(pending) == 1

        # Complete with structured data
        form_data = {"first_name": "Bob", "email": "bob@example.com"}
        await engine.complete_task(pending[0].id, TaskResult.ok(output=form_data))

        # Verify structured data stored in process properties
        process = await store.load_process(process.id)
        assert process.properties["__task_output_form_task"] == form_data
        assert process.state == ProcessState.COMPLETE


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
                "branch_a": TaskDefinition(id="branch_a", name="Branch A", auto=False),
                "branch_b": TaskDefinition(id="branch_b", name="Branch B", auto=False),
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


# ===========================================================================
# fail_process() Tests
# ===========================================================================


def _human_task_definition():
    """A workflow with a human task that stays in READY state."""
    return ProcessDefinition(
        id="human-wf",
        name="Human Workflow",
        version=1,
        first_task_id="manual",
        tasks={
            "manual": TaskDefinition(id="manual", name="Manual Step", auto=False),
            "done": TaskDefinition(id="done", name="Done", auto=True),
        },
        routings=[
            RoutingDefinition(id="r1", source_task_id="manual", dest_task_id="done"),
        ],
    )


class TestFailProcess:
    """Tests for WorkflowEngine.fail_process()."""

    async def test_fail_running_process(self, engine, store):
        """A running process can be moved to FAILED state."""
        defn = _human_task_definition()
        process = await engine.create_process(defn)
        await engine.start_process(process.id)

        result = await engine.fail_process(process.id, "Timed out")

        assert result.state == ProcessState.FAILED
        assert result.properties["__error__"] == "Timed out"
        assert result.completed_at is not None

        # Verify persisted state
        reloaded = await store.load_process(process.id)
        assert reloaded.state == ProcessState.FAILED

    async def test_fail_paused_process(self, engine, store):
        """A paused process can also be failed."""
        defn = _human_task_definition()
        process = await engine.create_process(defn)
        await engine.start_process(process.id)
        await engine.pause_process(process.id)

        result = await engine.fail_process(process.id, "Cancelled")
        assert result.state == ProcessState.FAILED

    async def test_fail_created_process(self, engine, store):
        """A CREATED (not yet started) process can be failed."""
        defn = _human_task_definition()
        process = await engine.create_process(defn)

        result = await engine.fail_process(process.id, "No longer needed")
        assert result.state == ProcessState.FAILED

    async def test_fail_completed_process_raises(self, engine, simple_definition):
        """Cannot fail a process that is already COMPLETE."""
        process = await engine.create_process(simple_definition)
        await engine.start_process(process.id)

        with pytest.raises(InvalidStateTransitionError, match="terminal state"):
            await engine.fail_process(process.id, "Too late")

    async def test_fail_already_failed_process_raises(self, engine, store):
        """Cannot fail a process that is already FAILED."""
        defn = _human_task_definition()
        process = await engine.create_process(defn)
        await engine.start_process(process.id)
        await engine.fail_process(process.id, "First failure")

        with pytest.raises(InvalidStateTransitionError, match="terminal state"):
            await engine.fail_process(process.id, "Second failure")

    async def test_fail_sets_tasks_to_failed(self, engine, store):
        """All non-terminal tasks are moved to FAILED when process is failed."""
        defn = _human_task_definition()
        process = await engine.create_process(defn)
        await engine.start_process(process.id)

        # Verify task is READY before failing
        pending = await engine.get_pending_tasks(process.id)
        assert len(pending) == 1
        assert pending[0].state == TaskState.READY

        await engine.fail_process(process.id, "Cleanup")

        # Check the task is now FAILED
        tasks = await store.load_tasks_for_process(process.id)
        for task in tasks:
            assert task.state == TaskState.FAILED
            assert task.error == "Cleanup"
            assert task.completed_at is not None

    async def test_fail_process_not_found_raises(self, engine):
        """Failing a non-existent process raises ProcessNotFoundError."""
        with pytest.raises(ProcessNotFoundError):
            await engine.fail_process("nonexistent-id", "reason")
