"""Tests for the metrics module."""

from datetime import UTC, datetime

import pytest

from zebra_agent.metrics import TaskExecution, WorkflowRun, WorkflowStats


class TestWorkflowRun:
    """Tests for WorkflowRun dataclass."""

    def test_create_run(self):
        """Test creating a workflow run."""
        run = WorkflowRun(
            id="test-id",
            workflow_name="TestWorkflow",
            goal="Test goal",
            started_at=datetime(2024, 1, 15, 10, 0, tzinfo=UTC),
        )
        assert run.id == "test-id"
        assert run.workflow_name == "TestWorkflow"
        assert run.goal == "Test goal"
        assert run.success is False
        assert run.completed_at is None

    def test_create_factory(self):
        """Test the create factory method."""
        run = WorkflowRun.create("TestWorkflow", "Test goal")
        assert run.workflow_name == "TestWorkflow"
        assert run.goal == "Test goal"
        assert run.id is not None
        assert len(run.id) == 36  # UUID length
        assert run.started_at is not None
        assert run.started_at.tzinfo is not None

    def test_run_with_all_fields(self):
        """Test run with all fields populated."""
        run = WorkflowRun(
            id="test-id",
            workflow_name="TestWorkflow",
            goal="Test goal",
            started_at=datetime(2024, 1, 15, 10, 0, tzinfo=UTC),
            completed_at=datetime(2024, 1, 15, 10, 5, tzinfo=UTC),
            success=True,
            user_rating=5,
            tokens_used=100,
            error=None,
            output={"result": "success"},
        )
        assert run.success is True
        assert run.user_rating == 5
        assert run.tokens_used == 100
        assert run.output == {"result": "success"}


class TestWorkflowStats:
    """Tests for WorkflowStats dataclass."""

    def test_create_stats(self):
        """Test creating workflow stats."""
        stats = WorkflowStats(
            workflow_name="TestWorkflow",
            total_runs=10,
            successful_runs=8,
            avg_rating=4.5,
            last_used=datetime(2024, 1, 15, 12, 0, tzinfo=UTC),
        )
        assert stats.workflow_name == "TestWorkflow"
        assert stats.total_runs == 10
        assert stats.successful_runs == 8

    def test_success_rate_with_runs(self):
        """Test success rate calculation."""
        stats = WorkflowStats(
            workflow_name="TestWorkflow",
            total_runs=10,
            successful_runs=8,
        )
        assert stats.success_rate == 0.8

    def test_success_rate_no_runs(self):
        """Test success rate when no runs."""
        stats = WorkflowStats(workflow_name="TestWorkflow")
        assert stats.success_rate == 0.0

    def test_success_rate_all_successful(self):
        """Test success rate when all runs are successful."""
        stats = WorkflowStats(
            workflow_name="TestWorkflow",
            total_runs=5,
            successful_runs=5,
        )
        assert stats.success_rate == 1.0

    def test_success_rate_none_successful(self):
        """Test success rate when no runs are successful."""
        stats = WorkflowStats(
            workflow_name="TestWorkflow",
            total_runs=5,
            successful_runs=0,
        )
        assert stats.success_rate == 0.0

    def test_default_values(self):
        """Test default values."""
        stats = WorkflowStats(workflow_name="TestWorkflow")
        assert stats.total_runs == 0
        assert stats.successful_runs == 0
        assert stats.avg_rating is None
        assert stats.last_used is None


class TestMetricsStoreInitialization:
    """Tests for MetricsStore initialization."""

    async def test_initialization(self, metrics):
        """Test that metrics initializes correctly."""
        await metrics._ensure_initialized()
        assert metrics._initialized is True

    async def test_double_initialization(self, metrics):
        """Test that double initialization is safe."""
        await metrics._ensure_initialized()
        await metrics._ensure_initialized()
        assert metrics._initialized is True


class TestRecordRun:
    """Tests for recording workflow runs."""

    async def test_record_run(self, metrics):
        """Test recording a workflow run."""
        run = WorkflowRun.create("TestWorkflow", "Test goal")
        run.completed_at = datetime.now(UTC)
        run.success = True
        run.tokens_used = 100

        await metrics.record_run(run)

        # Verify it was stored
        retrieved = await metrics.get_run(run.id)
        assert retrieved is not None
        assert retrieved.workflow_name == "TestWorkflow"
        assert retrieved.goal == "Test goal"
        assert retrieved.success is True

    async def test_record_run_with_error(self, metrics):
        """Test recording a failed run with error."""
        run = WorkflowRun.create("TestWorkflow", "Test goal")
        run.completed_at = datetime.now(UTC)
        run.success = False
        run.error = "Something went wrong"

        await metrics.record_run(run)

        retrieved = await metrics.get_run(run.id)
        assert retrieved is not None
        assert retrieved.success is False
        assert retrieved.error == "Something went wrong"

    async def test_record_run_with_output(self, metrics):
        """Test recording a run with output."""
        run = WorkflowRun.create("TestWorkflow", "Test goal")
        run.completed_at = datetime.now(UTC)
        run.success = True
        run.output = {"result": "test"}

        await metrics.record_run(run)

        retrieved = await metrics.get_run(run.id)
        assert retrieved is not None
        # Output is stored as string
        assert "result" in retrieved.output

    async def test_record_run_replaces_existing(self, metrics):
        """Test that recording with same ID replaces."""
        run = WorkflowRun(
            id="fixed-id",
            workflow_name="TestWorkflow",
            goal="Original goal",
            started_at=datetime.now(UTC),
        )
        await metrics.record_run(run)

        # Update and record again
        run.goal = "Updated goal"
        run.success = True
        run.completed_at = datetime.now(UTC)
        await metrics.record_run(run)

        retrieved = await metrics.get_run("fixed-id")
        assert retrieved.goal == "Updated goal"
        assert retrieved.success is True


class TestGetRun:
    """Tests for retrieving workflow runs."""

    async def test_get_run_exists(self, metrics):
        """Test getting an existing run."""
        run = WorkflowRun.create("TestWorkflow", "Test goal")
        await metrics.record_run(run)

        retrieved = await metrics.get_run(run.id)
        assert retrieved is not None
        assert retrieved.id == run.id

    async def test_get_run_not_exists(self, metrics):
        """Test getting a non-existent run."""
        retrieved = await metrics.get_run("nonexistent-id")
        assert retrieved is None

    async def test_get_run_preserves_all_fields(self, metrics):
        """Test that all fields are preserved on retrieval."""
        run = WorkflowRun(
            id="test-id",
            workflow_name="TestWorkflow",
            goal="Test goal",
            started_at=datetime(2024, 1, 15, 10, 0, tzinfo=UTC),
            completed_at=datetime(2024, 1, 15, 10, 5, tzinfo=UTC),
            success=True,
            user_rating=4,
            tokens_used=150,
            error=None,
            output="Test output",
        )
        await metrics.record_run(run)

        retrieved = await metrics.get_run(run.id)
        assert retrieved.workflow_name == "TestWorkflow"
        assert retrieved.goal == "Test goal"
        assert retrieved.started_at == datetime(2024, 1, 15, 10, 0, tzinfo=UTC)
        assert retrieved.completed_at == datetime(2024, 1, 15, 10, 5, tzinfo=UTC)
        assert retrieved.success is True
        assert retrieved.user_rating == 4
        assert retrieved.tokens_used == 150


class TestUpdateRating:
    """Tests for updating run ratings."""

    async def test_update_rating(self, metrics):
        """Test updating a run rating."""
        run = WorkflowRun.create("TestWorkflow", "Test goal")
        await metrics.record_run(run)

        await metrics.update_rating(run.id, 5)

        retrieved = await metrics.get_run(run.id)
        assert retrieved.user_rating == 5

    async def test_update_rating_invalid_low(self, metrics):
        """Test that invalid low rating raises error."""
        run = WorkflowRun.create("TestWorkflow", "Test goal")
        await metrics.record_run(run)

        with pytest.raises(ValueError, match="Rating must be between 1 and 5"):
            await metrics.update_rating(run.id, 0)

    async def test_update_rating_invalid_high(self, metrics):
        """Test that invalid high rating raises error."""
        run = WorkflowRun.create("TestWorkflow", "Test goal")
        await metrics.record_run(run)

        with pytest.raises(ValueError, match="Rating must be between 1 and 5"):
            await metrics.update_rating(run.id, 6)

    async def test_update_rating_min_valid(self, metrics):
        """Test minimum valid rating."""
        run = WorkflowRun.create("TestWorkflow", "Test goal")
        await metrics.record_run(run)

        await metrics.update_rating(run.id, 1)

        retrieved = await metrics.get_run(run.id)
        assert retrieved.user_rating == 1

    async def test_update_rating_max_valid(self, metrics):
        """Test maximum valid rating."""
        run = WorkflowRun.create("TestWorkflow", "Test goal")
        await metrics.record_run(run)

        await metrics.update_rating(run.id, 5)

        retrieved = await metrics.get_run(run.id)
        assert retrieved.user_rating == 5


class TestGetStats:
    """Tests for getting workflow statistics."""

    async def test_get_stats_no_runs(self, metrics):
        """Test getting stats when no runs exist."""
        stats = await metrics.get_stats("TestWorkflow")
        assert stats.workflow_name == "TestWorkflow"
        assert stats.total_runs == 0
        assert stats.successful_runs == 0

    async def test_get_stats_with_runs(self, metrics):
        """Test getting stats with runs."""
        # Create some runs
        for i in range(5):
            run = WorkflowRun.create("TestWorkflow", f"Goal {i}")
            run.completed_at = datetime.now(UTC)
            run.success = i < 3  # 3 successful, 2 failed
            if run.success:
                run.user_rating = 4
            await metrics.record_run(run)

        stats = await metrics.get_stats("TestWorkflow")
        assert stats.total_runs == 5
        assert stats.successful_runs == 3
        assert stats.success_rate == 0.6

    async def test_get_stats_with_ratings(self, metrics):
        """Test getting stats with ratings."""
        ratings = [3, 4, 5]
        for i, rating in enumerate(ratings):
            run = WorkflowRun.create("TestWorkflow", f"Goal {i}")
            run.completed_at = datetime.now(UTC)
            run.success = True
            run.user_rating = rating
            await metrics.record_run(run)

        stats = await metrics.get_stats("TestWorkflow")
        assert stats.avg_rating == 4.0  # (3+4+5)/3 = 4

    async def test_get_stats_filters_by_workflow(self, metrics):
        """Test that stats are filtered by workflow name."""
        # Create runs for different workflows
        for i in range(3):
            run = WorkflowRun.create("WorkflowA", f"Goal {i}")
            run.success = True
            await metrics.record_run(run)

        for i in range(2):
            run = WorkflowRun.create("WorkflowB", f"Goal {i}")
            run.success = True
            await metrics.record_run(run)

        stats_a = await metrics.get_stats("WorkflowA")
        stats_b = await metrics.get_stats("WorkflowB")

        assert stats_a.total_runs == 3
        assert stats_b.total_runs == 2


class TestGetAllStats:
    """Tests for getting all workflow statistics."""

    async def test_get_all_stats_empty(self, metrics):
        """Test getting all stats when no runs exist."""
        stats = await metrics.get_all_stats()
        assert stats == []

    async def test_get_all_stats_single_workflow(self, metrics):
        """Test getting all stats with single workflow."""
        run = WorkflowRun.create("TestWorkflow", "Test goal")
        run.success = True
        await metrics.record_run(run)

        stats = await metrics.get_all_stats()
        assert len(stats) == 1
        assert stats[0].workflow_name == "TestWorkflow"

    async def test_get_all_stats_multiple_workflows(self, metrics):
        """Test getting all stats with multiple workflows."""
        workflows = ["WorkflowA", "WorkflowB", "WorkflowC"]
        run_counts = [5, 3, 2]

        for workflow, count in zip(workflows, run_counts):
            for i in range(count):
                run = WorkflowRun.create(workflow, f"Goal {i}")
                run.success = True
                await metrics.record_run(run)

        stats = await metrics.get_all_stats()
        assert len(stats) == 3
        # Should be ordered by total_runs DESC
        assert stats[0].workflow_name == "WorkflowA"
        assert stats[0].total_runs == 5
        assert stats[1].workflow_name == "WorkflowB"
        assert stats[1].total_runs == 3
        assert stats[2].workflow_name == "WorkflowC"
        assert stats[2].total_runs == 2


class TestGetRecentRuns:
    """Tests for getting recent runs."""

    async def test_get_recent_runs_empty(self, metrics):
        """Test getting recent runs when none exist."""
        runs = await metrics.get_recent_runs()
        assert runs == []

    async def test_get_recent_runs_default_limit(self, metrics):
        """Test getting recent runs with default limit."""
        for i in range(15):
            run = WorkflowRun.create("TestWorkflow", f"Goal {i}")
            await metrics.record_run(run)

        runs = await metrics.get_recent_runs()
        assert len(runs) == 10  # Default limit

    async def test_get_recent_runs_custom_limit(self, metrics):
        """Test getting recent runs with custom limit."""
        for i in range(10):
            run = WorkflowRun.create("TestWorkflow", f"Goal {i}")
            await metrics.record_run(run)

        runs = await metrics.get_recent_runs(limit=3)
        assert len(runs) == 3

    async def test_get_recent_runs_order(self, metrics):
        """Test that recent runs are ordered by started_at DESC."""
        runs_to_create = []
        for i in range(5):
            run = WorkflowRun.create("TestWorkflow", f"Goal {i}")
            runs_to_create.append(run)
            await metrics.record_run(run)

        recent = await metrics.get_recent_runs(limit=5)
        # Should be most recent first
        assert recent[0].goal == "Goal 4"
        assert recent[-1].goal == "Goal 0"


class TestRowToRun:
    """Tests for the _row_to_run helper method."""

    async def test_row_to_run_with_completed_at(self, metrics):
        """Test conversion with completed_at set."""
        run = WorkflowRun.create("TestWorkflow", "Test goal")
        run.completed_at = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)
        run.success = True
        await metrics.record_run(run)

        retrieved = await metrics.get_run(run.id)
        assert retrieved.completed_at == datetime(2024, 1, 15, 12, 0, tzinfo=UTC)

    async def test_row_to_run_without_completed_at(self, metrics):
        """Test conversion without completed_at set."""
        run = WorkflowRun.create("TestWorkflow", "Test goal")
        await metrics.record_run(run)

        retrieved = await metrics.get_run(run.id)
        assert retrieved.completed_at is None

    async def test_row_to_run_success_conversion(self, metrics):
        """Test that success is properly converted to bool."""
        # Test successful
        run_success = WorkflowRun.create("TestWorkflow", "Goal 1")
        run_success.success = True
        await metrics.record_run(run_success)

        # Test failed
        run_failed = WorkflowRun.create("TestWorkflow", "Goal 2")
        run_failed.success = False
        await metrics.record_run(run_failed)

        retrieved_success = await metrics.get_run(run_success.id)
        retrieved_failed = await metrics.get_run(run_failed.id)

        assert retrieved_success.success is True
        assert retrieved_failed.success is False

    async def test_row_to_run_tokens_default(self, metrics):
        """Test that tokens_used defaults to 0."""
        run = WorkflowRun.create("TestWorkflow", "Test goal")
        await metrics.record_run(run)

        retrieved = await metrics.get_run(run.id)
        assert retrieved.tokens_used == 0


class TestTaskExecution:
    """Tests for TaskExecution dataclass."""

    def test_create_task_execution(self):
        """Test creating a task execution."""
        exec = TaskExecution(
            id="test-id",
            run_id="run-123",
            task_definition_id="analyze",
            task_name="Analyze Input",
            execution_order=1,
            state="complete",
            started_at=datetime(2024, 1, 15, 10, 0, tzinfo=UTC),
        )
        assert exec.id == "test-id"
        assert exec.run_id == "run-123"
        assert exec.task_definition_id == "analyze"
        assert exec.task_name == "Analyze Input"
        assert exec.execution_order == 1
        assert exec.state == "complete"

    def test_create_factory(self):
        """Test the create factory method."""
        exec = TaskExecution.create(
            run_id="run-123",
            task_definition_id="process",
            task_name="Process Data",
            execution_order=2,
        )
        assert exec.run_id == "run-123"
        assert exec.task_definition_id == "process"
        assert exec.task_name == "Process Data"
        assert exec.execution_order == 2
        assert exec.state == "running"
        assert exec.id is not None
        assert len(exec.id) == 36  # UUID length
        assert exec.started_at is not None

    def test_execution_with_all_fields(self):
        """Test execution with all fields populated."""
        exec = TaskExecution(
            id="test-id",
            run_id="run-123",
            task_definition_id="summarize",
            task_name="Summarize Results",
            execution_order=3,
            state="complete",
            started_at=datetime(2024, 1, 15, 10, 0, tzinfo=UTC),
            completed_at=datetime(2024, 1, 15, 10, 1, tzinfo=UTC),
            output={"summary": "Test summary"},
            error=None,
        )
        assert exec.completed_at is not None
        assert exec.output == {"summary": "Test summary"}
        assert exec.error is None

    def test_execution_failed_state(self):
        """Test execution with failed state and error."""
        exec = TaskExecution(
            id="test-id",
            run_id="run-123",
            task_definition_id="failing_task",
            task_name="Failing Task",
            execution_order=1,
            state="failed",
            started_at=datetime(2024, 1, 15, 10, 0, tzinfo=UTC),
            completed_at=datetime(2024, 1, 15, 10, 0, 30, tzinfo=UTC),
            error="Something went wrong",
        )
        assert exec.state == "failed"
        assert exec.error == "Something went wrong"


class TestRecordTaskExecution:
    """Tests for recording task executions."""

    async def test_record_task_execution(self, metrics):
        """Test recording a task execution."""
        # First create a workflow run (needed for foreign key)
        run = WorkflowRun.create("TestWorkflow", "Test goal")
        await metrics.record_run(run)

        # Create and record task execution
        exec = TaskExecution.create(
            run_id=run.id,
            task_definition_id="analyze",
            task_name="Analyze",
            execution_order=1,
        )
        exec.state = "complete"
        exec.completed_at = datetime.now(UTC)
        exec.output = {"result": "success"}

        await metrics.record_task_execution(exec)

        # Verify it was stored
        executions = await metrics.get_task_executions(run.id)
        assert len(executions) == 1
        assert executions[0].task_definition_id == "analyze"
        assert executions[0].state == "complete"

    async def test_record_task_execution_with_dict_output(self, metrics):
        """Test recording task execution with dict output."""
        run = WorkflowRun.create("TestWorkflow", "Test goal")
        await metrics.record_run(run)

        exec = TaskExecution.create(
            run_id=run.id,
            task_definition_id="process",
            task_name="Process",
            execution_order=1,
        )
        exec.state = "complete"
        exec.output = {"key": "value", "nested": {"inner": 42}}

        await metrics.record_task_execution(exec)

        executions = await metrics.get_task_executions(run.id)
        assert len(executions) == 1
        assert executions[0].output == {"key": "value", "nested": {"inner": 42}}

    async def test_record_task_execution_with_string_output(self, metrics):
        """Test recording task execution with string output."""
        run = WorkflowRun.create("TestWorkflow", "Test goal")
        await metrics.record_run(run)

        exec = TaskExecution.create(
            run_id=run.id,
            task_definition_id="summarize",
            task_name="Summarize",
            execution_order=1,
        )
        exec.state = "complete"
        exec.output = "This is a plain string output"

        await metrics.record_task_execution(exec)

        executions = await metrics.get_task_executions(run.id)
        assert len(executions) == 1
        assert executions[0].output == "This is a plain string output"

    async def test_record_multiple_task_executions(self, metrics):
        """Test recording multiple task executions for a run."""
        run = WorkflowRun.create("TestWorkflow", "Test goal")
        await metrics.record_run(run)

        # Record multiple executions
        for i, task_id in enumerate(["start", "process", "finish"], 1):
            exec = TaskExecution.create(
                run_id=run.id,
                task_definition_id=task_id,
                task_name=task_id.capitalize(),
                execution_order=i,
            )
            exec.state = "complete"
            exec.completed_at = datetime.now(UTC)
            await metrics.record_task_execution(exec)

        executions = await metrics.get_task_executions(run.id)
        assert len(executions) == 3
        # Should be ordered by execution_order
        assert executions[0].task_definition_id == "start"
        assert executions[1].task_definition_id == "process"
        assert executions[2].task_definition_id == "finish"

    async def test_record_task_executions_batch(self, metrics):
        """Test batch recording task executions."""
        run = WorkflowRun.create("TestWorkflow", "Test goal")
        await metrics.record_run(run)

        executions_to_record = []
        for i in range(3):
            exec = TaskExecution.create(
                run_id=run.id,
                task_definition_id=f"task_{i}",
                task_name=f"Task {i}",
                execution_order=i + 1,
            )
            exec.state = "complete"
            executions_to_record.append(exec)

        await metrics.record_task_executions(executions_to_record)

        executions = await metrics.get_task_executions(run.id)
        assert len(executions) == 3

    async def test_record_task_execution_with_error(self, metrics):
        """Test recording a failed task execution."""
        run = WorkflowRun.create("TestWorkflow", "Test goal")
        await metrics.record_run(run)

        exec = TaskExecution.create(
            run_id=run.id,
            task_definition_id="failing_task",
            task_name="Failing Task",
            execution_order=1,
        )
        exec.state = "failed"
        exec.completed_at = datetime.now(UTC)
        exec.error = "Task failed with error"

        await metrics.record_task_execution(exec)

        executions = await metrics.get_task_executions(run.id)
        assert len(executions) == 1
        assert executions[0].state == "failed"
        assert executions[0].error == "Task failed with error"


class TestGetTaskExecutions:
    """Tests for getting task executions."""

    async def test_get_task_executions_empty(self, metrics):
        """Test getting task executions when none exist."""
        run = WorkflowRun.create("TestWorkflow", "Test goal")
        await metrics.record_run(run)

        executions = await metrics.get_task_executions(run.id)
        assert executions == []

    async def test_get_task_executions_ordered(self, metrics):
        """Test that task executions are ordered by execution_order."""
        run = WorkflowRun.create("TestWorkflow", "Test goal")
        await metrics.record_run(run)

        # Record in non-sequential order
        for order in [3, 1, 2]:
            exec = TaskExecution(
                id=f"exec-{order}",
                run_id=run.id,
                task_definition_id=f"task_{order}",
                task_name=f"Task {order}",
                execution_order=order,
                state="complete",
                started_at=datetime.now(UTC),
            )
            await metrics.record_task_execution(exec)

        executions = await metrics.get_task_executions(run.id)
        assert len(executions) == 3
        assert executions[0].execution_order == 1
        assert executions[1].execution_order == 2
        assert executions[2].execution_order == 3

    async def test_get_task_executions_filters_by_run(self, metrics):
        """Test that task executions are filtered by run_id."""
        # Create two runs
        run1 = WorkflowRun.create("TestWorkflow", "Goal 1")
        run2 = WorkflowRun.create("TestWorkflow", "Goal 2")
        await metrics.record_run(run1)
        await metrics.record_run(run2)

        # Add executions to each run
        for run, count in [(run1, 2), (run2, 3)]:
            for i in range(count):
                exec = TaskExecution.create(
                    run_id=run.id,
                    task_definition_id=f"task_{i}",
                    task_name=f"Task {i}",
                    execution_order=i + 1,
                )
                exec.state = "complete"
                await metrics.record_task_execution(exec)

        exec1 = await metrics.get_task_executions(run1.id)
        exec2 = await metrics.get_task_executions(run2.id)

        assert len(exec1) == 2
        assert len(exec2) == 3

    async def test_get_task_executions_nonexistent_run(self, metrics):
        """Test getting task executions for nonexistent run."""
        executions = await metrics.get_task_executions("nonexistent-run-id")
        assert executions == []
