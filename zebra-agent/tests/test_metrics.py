"""Tests for the metrics module."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from zebra_agent.metrics import MetricsStore, WorkflowRun, WorkflowStats


@pytest.fixture
def temp_db():
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield Path(f.name)
    # Cleanup
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture
def metrics(temp_db):
    """Create a MetricsStore instance."""
    return MetricsStore(temp_db)


class TestWorkflowRun:
    """Tests for WorkflowRun dataclass."""

    def test_create_run(self):
        """Test creating a workflow run."""
        run = WorkflowRun(
            id="test-id",
            workflow_name="TestWorkflow",
            goal="Test goal",
            started_at=datetime(2024, 1, 15, 10, 0),
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

    def test_run_with_all_fields(self):
        """Test run with all fields populated."""
        run = WorkflowRun(
            id="test-id",
            workflow_name="TestWorkflow",
            goal="Test goal",
            started_at=datetime(2024, 1, 15, 10, 0),
            completed_at=datetime(2024, 1, 15, 10, 5),
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
            last_used=datetime(2024, 1, 15, 12, 0),
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

    async def test_creates_directory(self, temp_db):
        """Test that metrics creates parent directories."""
        nested_path = temp_db.parent / "metrics_subdir" / "metrics.db"
        metrics = MetricsStore(nested_path)
        await metrics._ensure_initialized()
        assert nested_path.parent.exists()
        # Cleanup
        nested_path.unlink(missing_ok=True)
        nested_path.parent.rmdir()

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
        run.completed_at = datetime.now()
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
        run.completed_at = datetime.now()
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
        run.completed_at = datetime.now()
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
            started_at=datetime.now(),
        )
        await metrics.record_run(run)

        # Update and record again
        run.goal = "Updated goal"
        run.success = True
        run.completed_at = datetime.now()
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
            started_at=datetime(2024, 1, 15, 10, 0),
            completed_at=datetime(2024, 1, 15, 10, 5),
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
        assert retrieved.started_at == datetime(2024, 1, 15, 10, 0)
        assert retrieved.completed_at == datetime(2024, 1, 15, 10, 5)
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
            run.completed_at = datetime.now()
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
            run.completed_at = datetime.now()
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
        run.completed_at = datetime(2024, 1, 15, 12, 0)
        run.success = True
        await metrics.record_run(run)

        retrieved = await metrics.get_run(run.id)
        assert retrieved.completed_at == datetime(2024, 1, 15, 12, 0)

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
