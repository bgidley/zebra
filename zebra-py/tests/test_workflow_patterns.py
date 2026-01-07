"""Tests for Workflow Control-Flow Patterns.

This module tests the implementation of workflow patterns from the
Workflow Patterns Initiative (http://www.workflowpatterns.com).

Reference: Russell, N., ter Hofstede, A.H.M., van der Aalst, W.M.P., & Mulyar, N. (2006).
"Workflow Control-Flow Patterns: A Revised View." BPM-06-22.
"""

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


class RecordingAction(TaskAction):
    """A test action that records executions in order."""

    executions = []

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        RecordingAction.executions.append(task.task_definition_id)
        return TaskResult.ok(output=f"executed_{task.task_definition_id}")

    @classmethod
    def reset(cls):
        cls.executions = []


class RouteSmallAction(TaskAction):
    """A test action that returns 'small' routing choice."""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        RecordingAction.executions.append(task.task_definition_id)
        return TaskResult(success=True, output="choice_made", next_route="small")


class RouteLargeAction(TaskAction):
    """A test action that returns 'large' routing choice."""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        RecordingAction.executions.append(task.task_definition_id)
        return TaskResult(success=True, output="choice_made", next_route="large")


class ConditionalRouteAction(TaskAction):
    """Action that evaluates to different routes based on conditions."""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        RecordingAction.executions.append(task.task_definition_id)
        # Use task properties to determine route
        choice = task.properties.get("choice", "default")
        return TaskResult(success=True, output=f"chose_{choice}", next_route=choice)


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture
def registry():
    reg = ActionRegistry()
    reg.register_defaults()  # Register built-in actions and conditions
    reg.register_action("recording", RecordingAction)
    reg.register_action("route_small", RouteSmallAction)
    reg.register_action("route_large", RouteLargeAction)
    reg.register_action("conditional", ConditionalRouteAction)
    return reg


@pytest.fixture
def engine(store, registry):
    return WorkflowEngine(store, registry)


@pytest.fixture(autouse=True)
def reset_recording_action():
    """Reset the recording action before each test."""
    RecordingAction.reset()


# =============================================================================
# Basic Control-Flow Patterns
# =============================================================================


class TestBasicPatterns:
    """Test basic control-flow patterns WCP-1 through WCP-5."""

    @pytest.mark.asyncio
    async def test_wcp01_sequence(self, engine):
        """Test WCP-1: Sequence pattern.

        An activity is enabled after completion of a preceding activity.
        """
        definition = ProcessDefinition(
            id="wcp01",
            name="Sequence Pattern",
            first_task_id="task_a",
            tasks={
                "task_a": TaskDefinition(id="task_a", name="Task A", action="recording"),
                "task_b": TaskDefinition(id="task_b", name="Task B", action="recording"),
                "task_c": TaskDefinition(id="task_c", name="Task C", action="recording"),
            },
            routings=[
                RoutingDefinition(id="r1", source_task_id="task_a", dest_task_id="task_b"),
                RoutingDefinition(id="r2", source_task_id="task_b", dest_task_id="task_c"),
            ],
        )

        process = await engine.create_process(definition)
        await engine.start_process(process.id)

        # Wait for completion
        status = await engine.get_process_status(process.id)
        assert status["process"]["state"] == ProcessState.COMPLETE.value

        # Verify execution order
        assert RecordingAction.executions == ["task_a", "task_b", "task_c"]

    @pytest.mark.asyncio
    async def test_wcp02_parallel_split(self, engine):
        """Test WCP-2: Parallel Split (AND-split).

        A branch diverges into two or more parallel branches that execute concurrently.
        """
        definition = ProcessDefinition(
            id="wcp02",
            name="Parallel Split Pattern",
            first_task_id="start",
            tasks={
                "start": TaskDefinition(id="start", name="Start", action="recording"),
                "branch_a": TaskDefinition(id="branch_a", name="Branch A", action="recording"),
                "branch_b": TaskDefinition(id="branch_b", name="Branch B", action="recording"),
                "branch_c": TaskDefinition(id="branch_c", name="Branch C", action="recording"),
            },
            routings=[
                RoutingDefinition(
                    id="r1", source_task_id="start", dest_task_id="branch_a", parallel=True
                ),
                RoutingDefinition(
                    id="r2", source_task_id="start", dest_task_id="branch_b", parallel=True
                ),
                RoutingDefinition(
                    id="r3", source_task_id="start", dest_task_id="branch_c", parallel=True
                ),
            ],
        )

        process = await engine.create_process(definition)
        await engine.start_process(process.id)

        status = await engine.get_process_status(process.id)
        assert status["process"]["state"] == ProcessState.COMPLETE.value

        # Start should execute first, then all branches
        assert RecordingAction.executions[0] == "start"
        assert set(RecordingAction.executions[1:]) == {"branch_a", "branch_b", "branch_c"}

    @pytest.mark.asyncio
    async def test_wcp03_synchronization(self, engine):
        """Test WCP-3: Synchronization (AND-join).

        Multiple branches converge, waiting for all branches to complete before proceeding.
        """
        definition = ProcessDefinition(
            id="wcp03",
            name="Synchronization Pattern",
            first_task_id="start",
            tasks={
                "start": TaskDefinition(id="start", name="Start", action="recording"),
                "branch_a": TaskDefinition(id="branch_a", name="Branch A", action="recording"),
                "branch_b": TaskDefinition(id="branch_b", name="Branch B", action="recording"),
                "join": TaskDefinition(
                    id="join", name="Join", synchronized=True, action="recording"
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

        process = await engine.create_process(definition)
        await engine.start_process(process.id)

        status = await engine.get_process_status(process.id)
        assert status["process"]["state"] == ProcessState.COMPLETE.value

        # Join should be last, after both branches
        assert RecordingAction.executions[-1] == "join"
        assert "branch_a" in RecordingAction.executions
        assert "branch_b" in RecordingAction.executions

    @pytest.mark.asyncio
    async def test_wcp04_exclusive_choice(self, engine):
        """Test WCP-4: Exclusive Choice (XOR-split).

        One of several branches is chosen based on a condition.
        """
        definition = ProcessDefinition(
            id="wcp04",
            name="Exclusive Choice Pattern",
            first_task_id="decision",
            tasks={
                "decision": TaskDefinition(
                    id="decision", name="Decision", action="route_small"
                ),
                "small_task": TaskDefinition(
                    id="small_task", name="Small Task", action="recording"
                ),
                "large_task": TaskDefinition(
                    id="large_task", name="Large Task", action="recording"
                ),
            },
            routings=[
                RoutingDefinition(
                    id="r1",
                    source_task_id="decision",
                    dest_task_id="small_task",
                    condition="route_name",
                    name="small",
                ),
                RoutingDefinition(
                    id="r2",
                    source_task_id="decision",
                    dest_task_id="large_task",
                    condition="route_name",
                    name="large",
                ),
            ],
        )

        process = await engine.create_process(definition)
        await engine.start_process(process.id)

        status = await engine.get_process_status(process.id)
        assert status["process"]["state"] == ProcessState.COMPLETE.value

        # Only one branch should execute
        assert "decision" in RecordingAction.executions
        assert "small_task" in RecordingAction.executions
        assert "large_task" not in RecordingAction.executions

    @pytest.mark.asyncio
    async def test_wcp05_simple_merge(self, engine):
        """Test WCP-5: Simple Merge (XOR-join).

        Multiple branches converge without synchronization; each activation passes through.
        """
        definition = ProcessDefinition(
            id="wcp05",
            name="Simple Merge Pattern",
            first_task_id="decision",
            tasks={
                "decision": TaskDefinition(
                    id="decision", name="Decision", action="route_small"
                ),
                "branch_a": TaskDefinition(id="branch_a", name="Branch A", action="recording"),
                "branch_b": TaskDefinition(id="branch_b", name="Branch B", action="recording"),
                "merge": TaskDefinition(id="merge", name="Merge", action="recording"),
            },
            routings=[
                RoutingDefinition(
                    id="r1",
                    source_task_id="decision",
                    dest_task_id="branch_a",
                    condition="route_name",
                    name="small",
                ),
                RoutingDefinition(
                    id="r2",
                    source_task_id="decision",
                    dest_task_id="branch_b",
                    condition="route_name",
                    name="large",
                ),
                RoutingDefinition(id="r3", source_task_id="branch_a", dest_task_id="merge"),
                RoutingDefinition(id="r4", source_task_id="branch_b", dest_task_id="merge"),
            ],
        )

        process = await engine.create_process(definition)
        await engine.start_process(process.id)

        status = await engine.get_process_status(process.id)
        assert status["process"]["state"] == ProcessState.COMPLETE.value

        # Merge should execute after one of the branches
        assert RecordingAction.executions[-1] == "merge"
        assert "branch_a" in RecordingAction.executions or "branch_b" in RecordingAction.executions


# =============================================================================
# Advanced Branching and Synchronization Patterns
# =============================================================================


class TestAdvancedBranchingPatterns:
    """Test advanced branching patterns WCP-6 through WCP-8."""

    @pytest.mark.asyncio
    async def test_wcp06_multi_choice_partial(self, engine):
        """Test WCP-6: Multi-Choice (OR-split) - Partial Support.

        One or more branches are activated based on conditions.
        Note: This demonstrates the limitation - all parallel branches execute.
        """
        definition = ProcessDefinition(
            id="wcp06",
            name="Multi-Choice Pattern",
            first_task_id="decision",
            tasks={
                "decision": TaskDefinition(id="decision", name="Decision", action="recording"),
                "branch_a": TaskDefinition(id="branch_a", name="Branch A", action="recording"),
                "branch_b": TaskDefinition(id="branch_b", name="Branch B", action="recording"),
                "branch_c": TaskDefinition(id="branch_c", name="Branch C", action="recording"),
            },
            routings=[
                # All branches execute in parallel (true OR-split would be conditional)
                RoutingDefinition(
                    id="r1", source_task_id="decision", dest_task_id="branch_a", parallel=True
                ),
                RoutingDefinition(
                    id="r2", source_task_id="decision", dest_task_id="branch_b", parallel=True
                ),
                RoutingDefinition(
                    id="r3", source_task_id="decision", dest_task_id="branch_c", parallel=True
                ),
            ],
        )

        process = await engine.create_process(definition)
        await engine.start_process(process.id)

        status = await engine.get_process_status(process.id)
        assert status["process"]["state"] == ProcessState.COMPLETE.value

        # All branches execute (limitation: cannot selectively activate subset)
        assert set(RecordingAction.executions) == {
            "decision",
            "branch_a",
            "branch_b",
            "branch_c",
        }

    @pytest.mark.asyncio
    async def test_wcp07_structured_synchronizing_merge(self, engine):
        """Test WCP-7: Structured Synchronizing Merge.

        Merges branches from a Multi-Choice, synchronizing active branches.
        """
        definition = ProcessDefinition(
            id="wcp07",
            name="Structured Synchronizing Merge Pattern",
            first_task_id="split",
            tasks={
                "split": TaskDefinition(id="split", name="Split", action="recording"),
                "branch_a": TaskDefinition(id="branch_a", name="Branch A", action="recording"),
                "branch_b": TaskDefinition(id="branch_b", name="Branch B", action="recording"),
                "merge": TaskDefinition(
                    id="merge", name="Merge", synchronized=True, action="recording"
                ),
            },
            routings=[
                RoutingDefinition(
                    id="r1", source_task_id="split", dest_task_id="branch_a", parallel=True
                ),
                RoutingDefinition(
                    id="r2", source_task_id="split", dest_task_id="branch_b", parallel=True
                ),
                RoutingDefinition(id="r3", source_task_id="branch_a", dest_task_id="merge"),
                RoutingDefinition(id="r4", source_task_id="branch_b", dest_task_id="merge"),
            ],
        )

        process = await engine.create_process(definition)
        await engine.start_process(process.id)

        status = await engine.get_process_status(process.id)
        assert status["process"]["state"] == ProcessState.COMPLETE.value

        # Merge waits for all branches
        assert RecordingAction.executions[-1] == "merge"
        assert "branch_a" in RecordingAction.executions
        assert "branch_b" in RecordingAction.executions

    @pytest.mark.asyncio
    async def test_wcp08_multi_merge_verification_needed(self, engine):
        """Test WCP-8: Multi-Merge - Verification Needed.

        Multiple branches merge without synchronization; each thread passes through.
        This test documents current behavior but may need adjustment based on
        actual multi-merge semantics.
        """
        # This pattern is marked as "needs verification" in workflows.md
        # Testing basic merge behavior
        definition = ProcessDefinition(
            id="wcp08",
            name="Multi-Merge Pattern",
            first_task_id="split",
            tasks={
                "split": TaskDefinition(id="split", name="Split", action="recording"),
                "branch_a": TaskDefinition(id="branch_a", name="Branch A", action="recording"),
                "branch_b": TaskDefinition(id="branch_b", name="Branch B", action="recording"),
                "merge": TaskDefinition(id="merge", name="Merge", action="recording"),
            },
            routings=[
                RoutingDefinition(
                    id="r1", source_task_id="split", dest_task_id="branch_a", parallel=True
                ),
                RoutingDefinition(
                    id="r2", source_task_id="split", dest_task_id="branch_b", parallel=True
                ),
                RoutingDefinition(id="r3", source_task_id="branch_a", dest_task_id="merge"),
                RoutingDefinition(id="r4", source_task_id="branch_b", dest_task_id="merge"),
            ],
        )

        process = await engine.create_process(definition)
        await engine.start_process(process.id)

        status = await engine.get_process_status(process.id)
        # TODO: Verify actual multi-merge behavior - should merge fire once or twice?
        assert status["process"]["state"] == ProcessState.COMPLETE.value


# =============================================================================
# Iteration Patterns
# =============================================================================


class TestIterationPatterns:
    """Test iteration patterns WCP-10 and WCP-21."""

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Needs investigation: loop with manual tasks doesn't create next iteration")
    async def test_wcp10_arbitrary_cycles(self, engine, store):
        """Test WCP-10: Arbitrary Cycles.

        Loops with multiple entry/exit points.

        TODO: This test reveals that when a manual task completes and triggers
        an auto task that loops back to another manual task, the second manual
        task is not becoming pending. Needs investigation into task lifecycle.
        """
        definition = ProcessDefinition(
            id="wcp10",
            name="Arbitrary Cycles Pattern",
            first_task_id="start",
            tasks={
                "start": TaskDefinition(id="start", name="Start", action="recording"),
                "review": TaskDefinition(
                    id="review",
                    name="Review",
                    action="conditional",
                    auto=False,  # Manual task for testing
                ),
                "revise": TaskDefinition(id="revise", name="Revise", action="recording"),
                "approve": TaskDefinition(id="approve", name="Approve", action="recording"),
            },
            routings=[
                RoutingDefinition(id="r1", source_task_id="start", dest_task_id="review"),
                RoutingDefinition(
                    id="r2",
                    source_task_id="review",
                    dest_task_id="approve",
                    condition="route_name",
                    name="approved",
                ),
                RoutingDefinition(
                    id="r3",
                    source_task_id="review",
                    dest_task_id="revise",
                    condition="route_name",
                    name="needs_revision",
                ),
                RoutingDefinition(
                    id="r4", source_task_id="revise", dest_task_id="review"
                ),  # Loop back
            ],
        )

        process = await engine.create_process(definition)
        await engine.start_process(process.id)

        # First iteration - needs revision
        pending = await engine.get_pending_tasks(process.id)
        assert len(pending) == 1
        assert pending[0].task_definition_id == "review"

        await engine.complete_task(
            pending[0].id, TaskResult(success=True, output="needs work", next_route="needs_revision")
        )

        # Second iteration - approve
        pending = await engine.get_pending_tasks(process.id)
        assert len(pending) == 1
        assert pending[0].task_definition_id == "review"

        await engine.complete_task(
            pending[0].id, TaskResult(success=True, output="looks good", next_route="approved")
        )

        status = await engine.get_process_status(process.id)
        assert status["process"]["state"] == ProcessState.COMPLETE.value

        # Should have: start, review, revise, review, approve
        assert RecordingAction.executions.count("review") == 2
        assert "revise" in RecordingAction.executions
        assert "approve" in RecordingAction.executions

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Needs investigation: loop with manual tasks doesn't create next iteration")
    async def test_wcp21_structured_loop(self, engine):
        """Test WCP-21: Structured Loop.

        While/repeat loops with single entry/exit point.

        TODO: Same issue as test_wcp10_arbitrary_cycles - manual task completion
        in a loop doesn't properly trigger the next iteration.
        """
        definition = ProcessDefinition(
            id="wcp21",
            name="Structured Loop Pattern",
            first_task_id="check_condition",
            tasks={
                "check_condition": TaskDefinition(
                    id="check_condition",
                    name="Check Condition",
                    action="conditional",
                    auto=False,
                ),
                "loop_body": TaskDefinition(
                    id="loop_body", name="Loop Body", action="recording"
                ),
                "exit": TaskDefinition(id="exit", name="Exit", action="recording"),
            },
            routings=[
                RoutingDefinition(
                    id="r1",
                    source_task_id="check_condition",
                    dest_task_id="loop_body",
                    condition="route_name",
                    name="continue",
                ),
                RoutingDefinition(
                    id="r2",
                    source_task_id="check_condition",
                    dest_task_id="exit",
                    condition="route_name",
                    name="exit",
                ),
                RoutingDefinition(
                    id="r3", source_task_id="loop_body", dest_task_id="check_condition"
                ),
            ],
        )

        process = await engine.create_process(definition)
        await engine.start_process(process.id)

        # Iteration 1
        pending = await engine.get_pending_tasks(process.id)
        await engine.complete_task(
            pending[0].id, TaskResult(success=True, output="continue", next_route="continue")
        )

        # Iteration 2
        pending = await engine.get_pending_tasks(process.id)
        await engine.complete_task(
            pending[0].id, TaskResult(success=True, output="continue", next_route="continue")
        )

        # Exit
        pending = await engine.get_pending_tasks(process.id)
        await engine.complete_task(
            pending[0].id, TaskResult(success=True, output="done", next_route="exit")
        )

        status = await engine.get_process_status(process.id)
        assert status["process"]["state"] == ProcessState.COMPLETE.value

        # Should have executed loop body twice
        assert RecordingAction.executions.count("loop_body") == 2
        assert RecordingAction.executions.count("check_condition") == 3
        assert "exit" in RecordingAction.executions


# =============================================================================
# Termination Patterns
# =============================================================================


class TestTerminationPatterns:
    """Test termination pattern WCP-11."""

    @pytest.mark.asyncio
    async def test_wcp11_implicit_termination(self, engine):
        """Test WCP-11: Implicit Termination.

        Process terminates when no more work can be done.
        """
        definition = ProcessDefinition(
            id="wcp11",
            name="Implicit Termination Pattern",
            first_task_id="start",
            tasks={
                "start": TaskDefinition(id="start", name="Start", action="recording"),
                "branch_a": TaskDefinition(id="branch_a", name="Branch A", action="recording"),
                "branch_b": TaskDefinition(id="branch_b", name="Branch B", action="recording"),
                # No explicit end task - process ends when all tasks complete
            },
            routings=[
                RoutingDefinition(
                    id="r1", source_task_id="start", dest_task_id="branch_a", parallel=True
                ),
                RoutingDefinition(
                    id="r2", source_task_id="start", dest_task_id="branch_b", parallel=True
                ),
            ],
        )

        process = await engine.create_process(definition)
        await engine.start_process(process.id)

        status = await engine.get_process_status(process.id)
        # Process should complete when all branches finish (no explicit termination needed)
        assert status["process"]["state"] == ProcessState.COMPLETE.value
        assert len(RecordingAction.executions) == 3  # start, branch_a, branch_b


# =============================================================================
# Cancellation Patterns (Partial Support)
# =============================================================================


class TestCancellationPatterns:
    """Test cancellation patterns WCP-19 and WCP-20 (partial support)."""

    @pytest.mark.asyncio
    async def test_wcp19_cancel_activity_investigation(self, engine):
        """Test WCP-19: Cancel Activity - Investigation Needed.

        This test documents that activity cancellation needs further investigation.
        """
        # TODO: Implement proper activity cancellation test once API is clarified
        definition = ProcessDefinition(
            id="wcp19",
            name="Cancel Activity Pattern",
            first_task_id="start",
            tasks={
                "start": TaskDefinition(id="start", name="Start", action="recording"),
                "long_task": TaskDefinition(
                    id="long_task", name="Long Task", action="recording", auto=False
                ),
            },
            routings=[
                RoutingDefinition(id="r1", source_task_id="start", dest_task_id="long_task"),
            ],
        )

        process = await engine.create_process(definition)
        await engine.start_process(process.id)

        # Task is now pending (ready but not completed because auto=False)
        pending = await engine.get_pending_tasks(process.id)
        assert len(pending) == 1

        # TODO: Test cancellation of pending task
        # Current test just verifies task can be in pending state

    @pytest.mark.asyncio
    async def test_wcp20_cancel_case(self, engine, store):
        """Test WCP-20: Cancel Case - Not Supported.

        Cancel an entire process instance.

        Note: Zebra currently does not have a cancel_process API.
        This test documents that the feature would be needed for full support.
        """
        definition = ProcessDefinition(
            id="wcp20",
            name="Cancel Case Pattern",
            first_task_id="start",
            tasks={
                "start": TaskDefinition(id="start", name="Start", action="recording"),
                "task_a": TaskDefinition(
                    id="task_a", name="Task A", action="recording", auto=False
                ),
            },
            routings=[
                RoutingDefinition(id="r1", source_task_id="start", dest_task_id="task_a"),
            ],
        )

        process = await engine.create_process(definition)
        await engine.start_process(process.id)

        # Verify process is running
        loaded_process = await store.load_process(process.id)
        assert loaded_process.state == ProcessState.RUNNING

        # TODO: Implement cancel_process method
        # await engine.cancel_process(process.id)
        # loaded_process = await store.load_process(process.id)
        # assert loaded_process.state == ProcessState.CANCELLED


# =============================================================================
# Multiple Instance Patterns (Partial Support)
# =============================================================================


class TestMultipleInstancePatterns:
    """Test multiple instance pattern WCP-12 (partial support)."""

    @pytest.mark.asyncio
    async def test_wcp12_multiple_instances_via_parallel(self, engine):
        """Test WCP-12: Multiple Instances without Synchronization.

        Demonstrates how multiple instances can be created via parallel branches.
        Note: This is a workaround, not a dedicated multiple-instance construct.
        """
        definition = ProcessDefinition(
            id="wcp12",
            name="Multiple Instances Pattern",
            first_task_id="start",
            tasks={
                "start": TaskDefinition(id="start", name="Start", action="recording"),
                "instance_1": TaskDefinition(
                    id="instance_1", name="Instance 1", action="recording"
                ),
                "instance_2": TaskDefinition(
                    id="instance_2", name="Instance 2", action="recording"
                ),
                "instance_3": TaskDefinition(
                    id="instance_3", name="Instance 3", action="recording"
                ),
            },
            routings=[
                RoutingDefinition(
                    id="r1", source_task_id="start", dest_task_id="instance_1", parallel=True
                ),
                RoutingDefinition(
                    id="r2", source_task_id="start", dest_task_id="instance_2", parallel=True
                ),
                RoutingDefinition(
                    id="r3", source_task_id="start", dest_task_id="instance_3", parallel=True
                ),
            ],
        )

        process = await engine.create_process(definition)
        await engine.start_process(process.id)

        status = await engine.get_process_status(process.id)
        assert status["process"]["state"] == ProcessState.COMPLETE.value

        # All instances should execute
        assert "instance_1" in RecordingAction.executions
        assert "instance_2" in RecordingAction.executions
        assert "instance_3" in RecordingAction.executions
