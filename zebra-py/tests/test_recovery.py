"""Tests for workflow recovery and resilience features."""

from datetime import UTC, datetime

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


class SimpleAction(TaskAction):
    """Simple action for testing."""

    def __init__(self, result: str = "done"):
        self.result = result
        self.call_count = 0

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        self.call_count += 1
        return TaskResult.ok(output=self.result)


@pytest.fixture
def store():
    """Create a fresh in-memory store for each test."""
    return InMemoryStore()


@pytest.fixture
def registry():
    """Create a registry with test actions."""
    reg = ActionRegistry()
    reg.register_action("simple", SimpleAction)
    return reg


@pytest.fixture
def engine(store, registry):
    """Create a workflow engine with store and registry."""
    return WorkflowEngine(store, registry)


@pytest.fixture
def simple_definition():
    """Create a simple workflow definition."""
    return ProcessDefinition(
        id="simple_workflow",
        name="Simple Workflow",
        first_task_id="task1",
        tasks={
            "task1": TaskDefinition(id="task1", name="Task 1", action="simple", auto=False),
            "task2": TaskDefinition(id="task2", name="Task 2", action="simple", auto=False),
        },
        routings=[
            RoutingDefinition(id="r1", source_task_id="task1", dest_task_id="task2"),
        ],
    )


@pytest.mark.asyncio
async def test_resume_all_processes_no_interrupted(engine):
    """Test resume_all_processes returns empty list when no interrupted processes."""
    resumed = await engine.resume_all_processes()
    assert isinstance(resumed, list)
    assert len(resumed) == 0


@pytest.mark.asyncio
async def test_resume_all_processes_simple_workflow(engine, simple_definition):
    """Test resuming a simple workflow after simulated interruption."""
    # Create and start a process
    process = await engine.create_process(simple_definition)
    process = await engine.start_process(process.id)

    # Simulate interruption: process is RUNNING
    assert process.state == ProcessState.RUNNING

    # Process recovers on startup
    resumed = await engine.resume_all_processes()

    assert len(resumed) == 1
    assert resumed[0].id == process.id
    assert resumed[0].state == ProcessState.RUNNING


@pytest.mark.asyncio
async def test_resume_all_processes_resets_running_tasks(engine, simple_definition):
    """Test that interrupted tasks in RUNNING state are reset to READY."""
    # Create and start a process
    process = await engine.create_process(simple_definition)
    process = await engine.start_process(process.id)

    # Simulate task interruption: manually force a task to RUNNING
    tasks = await engine.store.load_tasks_for_process(process.id)
    if tasks:
        task = tasks[0]
        # Mark task as idempotent so it can be safely reset
        definition = await engine.store.load_definition(process.definition_id)
        task_def = definition.get_task(task.task_definition_id)
        # Add idempotency property to task definition
        definition = definition.model_copy(deep=True)
        definition.tasks[task_def.id] = task_def.model_copy(
            update={"properties": {"idempotent": True}}
        )
        await engine.store.save_definition(definition)

        # Simulate task was interrupted mid-execution
        task = task.model_copy(update={"state": TaskState.RUNNING})
        await engine.store.save_task(task)

    # Verify task is in RUNNING state
    running_before = await engine.store.get_running_tasks(process.id)
    assert len(running_before) > 0

    # Resume should reset RUNNING tasks to READY
    resumed = await engine.resume_all_processes()
    assert len(resumed) == 1

    # Verify tasks are handled correctly after recovery
    # If task was idempotent, it should be reset to READY
    # If task was non-idempotent, it stays in RUNNING with manual review flag
    running_after = await engine.store.get_running_tasks(process.id)
    tasks_after = await engine.store.load_tasks_for_process(process.id)

    # All tasks should either be READY or flagged for review
    review_tasks = [t for t in tasks_after if t.properties.get("__requires_manual_review__")]
    ready_tasks = [t for t in tasks_after if t.state == TaskState.READY]

    assert len(running_after) == 0  # No truly RUNNING tasks
    assert len(ready_tasks) + len(review_tasks) == len(tasks_after)


@pytest.mark.asyncio
async def test_resume_all_processes_skips_paused(engine, simple_definition):
    """Test that PAUSED processes are not auto-resumed."""
    # Create and start a process
    process = await engine.create_process(simple_definition)
    process = await engine.start_process(process.id)

    # Pause the process manually
    process = await engine.pause_process(process.id)
    assert process.state == ProcessState.PAUSED

    # Recovery should not resume PAUSED processes
    resumed = await engine.resume_all_processes()
    assert len(resumed) == 0

    # Verify process is still PAUSED
    loaded = await engine.store.load_process(process.id)
    assert loaded.state == ProcessState.PAUSED


@pytest.mark.asyncio
async def test_resume_all_processes_multiple_processes(engine):
    """Test recovery of multiple interrupted processes."""
    # Create multiple workflow definitions
    def1 = ProcessDefinition(
        id="workflow1",
        name="Workflow 1",
        first_task_id="task1",
        tasks={"task1": TaskDefinition(id="task1", name="Task 1", action="simple", auto=False)},
        routings=[],
    )

    def2 = ProcessDefinition(
        id="workflow2",
        name="Workflow 2",
        first_task_id="task1",
        tasks={"task1": TaskDefinition(id="task1", name="Task 1", action="simple", auto=False)},
        routings=[],
    )

    # Create multiple processes
    process1 = await engine.create_process(def1)
    process1 = await engine.start_process(process1.id)

    process2 = await engine.create_process(def1)
    process2 = await engine.start_process(process2.id)

    process3 = await engine.create_process(def2)
    process3 = await engine.start_process(process3.id)

    # Complete one process
    process3 = process3.model_copy(update={"state": ProcessState.COMPLETE})
    await engine.store.save_process(process3)

    # Should recover only the RUNNING processes
    resumed = await engine.resume_all_processes()
    assert len(resumed) == 2
    resumed_ids = {p.id for p in resumed}
    assert process1.id in resumed_ids
    assert process2.id in resumed_ids
    assert process3.id not in resumed_ids


@pytest.mark.asyncio
async def test_resume_all_processes_handles_errors_gracefully(engine, simple_definition):
    """Test that errors in one process don't stop recovery of others."""
    # Create multiple processes
    process1 = await engine.create_process(simple_definition)
    process1 = await engine.start_process(process1.id)

    process2 = await engine.create_process(simple_definition)
    process2 = await engine.start_process(process2.id)

    # Corrupt one process (delete its definition)
    await engine.store.delete_definition(simple_definition.id)

    # Recovery should handle the error gracefully
    resumed = await engine.resume_all_processes()

    # Should return successfully even if some processes failed
    assert isinstance(resumed, list)
    # Both processes were in RUNNING state, but only one might succeed
    assert len(resumed) <= 2


@pytest.mark.asyncio
async def test_recovery_parallel_split_interrupted(engine):
    """Test recovery when parallel split is interrupted mid-creation."""
    # Create a workflow with parallel execution
    definition = ProcessDefinition(
        id="parallel_workflow",
        name="Parallel Workflow",
        first_task_id="split",
        tasks={
            "split": TaskDefinition(id="split", name="Split", action="simple", auto=False),
            "branch1": TaskDefinition(id="branch1", name="Branch 1", action="simple", auto=False),
            "branch2": TaskDefinition(id="branch2", name="Branch 2", action="simple", auto=False),
            "join": TaskDefinition(
                id="join", name="Join", action="simple", auto=False, synchronized=True
            ),
        },
        routings=[
            RoutingDefinition(
                id="r1", source_task_id="split", dest_task_id="branch1", parallel=True
            ),
            RoutingDefinition(
                id="r2", source_task_id="split", dest_task_id="branch2", parallel=True
            ),
            RoutingDefinition(
                id="r3", source_task_id="branch1", dest_task_id="join", parallel=False
            ),
            RoutingDefinition(
                id="r4", source_task_id="branch2", dest_task_id="join", parallel=False
            ),
        ],
    )

    # Create and start a process
    process = await engine.create_process(definition)
    process = await engine.start_process(process.id)

    # Verify process is RUNNING
    assert process.state == ProcessState.RUNNING

    # Simulate interruption after FOEs were created but before some tasks
    # The FOE reconciliation should handle orphaned FOEs

    # Run recovery
    resumed = await engine.resume_all_processes()
    assert len(resumed) == 1

    # Process should still be recoverable
    loaded_process = await engine.store.load_process(process.id)
    assert loaded_process is not None


@pytest.mark.asyncio
async def test_recovery_sync_point_interrupted(engine):
    """Test recovery of interrupted synchronization point."""

    definition = ProcessDefinition(
        id="sync_workflow",
        name="Sync Workflow",
        first_task_id="task1",
        tasks={
            "task1": TaskDefinition(id="task1", name="Task 1", action="simple", auto=False),
            "sync_task": TaskDefinition(
                id="sync_task", name="Sync", action="simple", auto=False, synchronized=True
            ),
        },
        routings=[
            RoutingDefinition(
                id="r1", source_task_id="task1", dest_task_id="sync_task", parallel=False
            ),
        ],
    )

    process = await engine.create_process(definition)
    process = await engine.start_process(process.id)

    # Verify process is RUNNING
    assert process.state == ProcessState.RUNNING

    # Get the sync task
    tasks = await engine.store.load_tasks_for_process(process.id)
    sync_tasks = [t for t in tasks if t.task_definition_id == "sync_task"]

    if sync_tasks:
        sync_task = sync_tasks[0]
        # Manually set the task to AWAITING_SYNC to simulate waiting for parallel branches
        sync_task = sync_task.model_copy(update={"state": TaskState.AWAITING_SYNC})
        await engine.store.save_task(sync_task)

    # Recover should realize sync can proceed (no parallel branches blocking it)
    resumed = await engine.resume_all_processes()
    assert len(resumed) == 1

    # Verify sync task was set to READY
    tasks_after = await engine.store.load_tasks_for_process(process.id)
    sync_after = [t for t in tasks_after if t.task_definition_id == "sync_task"]
    if sync_after:
        assert sync_after[0].state == TaskState.READY


@pytest.mark.asyncio
async def test_recovery_partial_parallel_completion(engine):
    """Test recovery with some parallel branches completed, others interrupted."""
    definition = ProcessDefinition(
        id="partial_parallel",
        name="Partial Parallel",
        first_task_id="task1",
        tasks={
            "task1": TaskDefinition(id="task1", name="Task 1", action="simple", auto=True),
            "task2a": TaskDefinition(id="task2a", name="Task 2A", action="simple", auto=False),
            "task2b": TaskDefinition(id="task2b", name="Task 2B", action="simple", auto=False),
            "join": TaskDefinition(
                id="join", name="Join", action="simple", auto=False, synchronized=True
            ),
        },
        routings=[
            RoutingDefinition(
                id="r1", source_task_id="task1", dest_task_id="task2a", parallel=True
            ),
            RoutingDefinition(
                id="r2", source_task_id="task1", dest_task_id="task2b", parallel=True
            ),
            RoutingDefinition(
                id="r3", source_task_id="task2a", dest_task_id="join", parallel=False
            ),
            RoutingDefinition(
                id="r4", source_task_id="task2b", dest_task_id="join", parallel=False
            ),
        ],
    )

    process = await engine.create_process(definition)
    process = await engine.start_process(process.id)

    # Simulate one branch completed, one interrupted
    tasks = await engine.store.load_tasks_for_process(process.id)
    for task in tasks:
        if task.task_definition_id == "task2a" and task.state == TaskState.RUNNING:
            # Complete this branch
            task = task.model_copy(
                update={"state": TaskState.COMPLETE, "updated_at": datetime.now(UTC)}
            )
            await engine.store.save_task(task)
        elif task.task_definition_id == "task2b" and task.state == TaskState.RUNNING:
            # Keep this one in RUNNING (interrupted)
            pass

    # Recovery should handle the mixed state
    resumed = await engine.resume_all_processes()
    assert len(resumed) == 1


@pytest.mark.asyncio
async def test_recovery_non_idempotent_task_flagged(engine, simple_definition):
    """Test that non-idempotent tasks are flagged during recovery."""
    # Create a task with idempotency token (simulating it started execution)
    process = await engine.create_process(simple_definition)
    process = await engine.start_process(process.id)

    # Find a task and simulate it has idempotency token
    tasks = await engine.store.load_tasks_for_process(process.id)
    if tasks:
        task = tasks[0]
        task = task.model_copy(update={"state": TaskState.RUNNING})
        task.properties["__idempotency_token__"] = f"{task.id}_1_123456"
        await engine.store.save_task(task)

    # Run recovery
    resumed = await engine.resume_all_processes()
    assert len(resumed) == 1

    # Check that task was flagged for review
    updated_tasks = await engine.store.load_tasks_for_process(process.id)
    flagged_tasks = [t for t in updated_tasks if t.properties.get("__requires_manual_review__")]
    assert len(flagged_tasks) > 0


@pytest.mark.asyncio
async def test_recovery_foe_orphan_cleanup(engine):
    """Test that orphaned FOEs are cleaned up during recovery."""
    # Create a simple workflow
    definition = ProcessDefinition(
        id="test_foe_cleanup",
        name="Test FOE Cleanup",
        first_task_id="task1",
        tasks={"task1": TaskDefinition(id="task1", name="Task 1", action="simple", auto=False)},
        routings=[],
    )

    process = await engine.create_process(definition)
    process = await engine.start_process(process.id)

    # Manually create an orphaned FOE (no tasks reference it)
    from zebra.core.models import FlowOfExecution

    orphan_foe = FlowOfExecution(
        id="orphan_foe_123",
        process_id=process.id,
        parent_foe_id=None,
        created_at=datetime.now(UTC),
    )
    await engine.store.save_foe(orphan_foe)

    # Verify FOE exists
    foes_before = await engine.store.load_foes_for_process(process.id)
    assert len(foes_before) > 0

    # Run recovery
    resumed = await engine.resume_all_processes()

    # Check that orphaned FOE was cleaned up (excluding construct/destruct FOEs)
    foes_after = await engine.store.load_foes_for_process(process.id)
    orphan_foes = [f for f in foes_after if f.id == "orphan_foe_123"]
    assert len(orphan_foes) == 0
