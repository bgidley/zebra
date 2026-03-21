"""Tests for agent task actions."""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def temp_dir():
    """Create a temporary directory."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
async def metrics_db(temp_dir):
    """Create a test metrics database."""
    import aiosqlite

    db_path = temp_dir / "metrics.db"

    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS workflow_runs (
                id TEXT PRIMARY KEY,
                workflow_name TEXT,
                goal TEXT,
                started_at TEXT,
                completed_at TEXT,
                success INTEGER,
                user_rating INTEGER,
                tokens_used INTEGER,
                error TEXT,
                output TEXT
            )
        """)
        await db.commit()

    return db_path


@pytest.fixture
async def populated_metrics_db(metrics_db):
    """Create a metrics database with test data."""
    import aiosqlite

    # Use relative dates so data is within analysis window
    now = datetime.now()
    day1 = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    day2 = (now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S")
    day3 = (now - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S")

    async with aiosqlite.connect(metrics_db) as db:
        # Add some test runs
        runs = [
            ("run-1", "Answer Question", "What is 2+2?", day1, day1, 1, 5, 100, None),
            ("run-2", "Answer Question", "What is the capital of France?", day1, day1, 1, 4, 80, None),
            ("run-3", "Answer Question", "Explain quantum physics", day2, day2, 0, None, 200, "Timeout"),
            ("run-4", "Brainstorm Ideas", "Birthday party ideas", day2, day2, 1, 5, 150, None),
            ("run-5", "Brainstorm Ideas", "Business name ideas", day3, day3, 1, 3, 120, None),
            ("run-6", "Summarize Text", "Summarize this article", day3, day3, 0, None, 90, "Invalid input"),
        ]
        for run in runs:
            await db.execute("""
                INSERT INTO workflow_runs (id, workflow_name, goal, started_at, completed_at, success, user_rating, tokens_used, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, run)
        await db.commit()

    return metrics_db


@pytest.fixture
def mock_task():
    """Create a mock task instance."""
    task = MagicMock()
    task.properties = {}
    return task


@pytest.fixture
def mock_context():
    """Create a mock execution context."""
    context = MagicMock()
    context.process = MagicMock()
    context.process.properties = {}
    context.extras = {}
    context.get_process_property = MagicMock(side_effect=lambda k, d=None: context.process.properties.get(k, d))
    context.set_process_property = MagicMock(side_effect=lambda k, v: context.process.properties.__setitem__(k, v))
    context.resolve_template = MagicMock(side_effect=lambda x: x)
    return context


class TestMetricsAnalyzerAction:
    """Tests for MetricsAnalyzerAction."""

    @pytest.fixture
    async def empty_metrics_store(self):
        """Create an empty InMemoryMetricsStore."""
        from zebra_agent.storage.metrics import InMemoryMetricsStore

        store = InMemoryMetricsStore()
        await store.initialize()
        return store

    @pytest.fixture
    async def populated_metrics_store(self):
        """Create an InMemoryMetricsStore with test data."""
        from zebra_agent.metrics import WorkflowRun
        from zebra_agent.storage.metrics import InMemoryMetricsStore

        store = InMemoryMetricsStore()
        await store.initialize()

        now = datetime.now()
        day1 = now - timedelta(days=1)
        day2 = now - timedelta(days=2)
        day3 = now - timedelta(days=3)

        runs = [
            WorkflowRun(id="run-1", workflow_name="Answer Question", goal="What is 2+2?",
                        started_at=day1, completed_at=day1, success=True, user_rating=5, tokens_used=100),
            WorkflowRun(id="run-2", workflow_name="Answer Question", goal="What is the capital of France?",
                        started_at=day1, completed_at=day1, success=True, user_rating=4, tokens_used=80),
            WorkflowRun(id="run-3", workflow_name="Answer Question", goal="Explain quantum physics",
                        started_at=day2, completed_at=day2, success=False, tokens_used=200, error="Timeout"),
            WorkflowRun(id="run-4", workflow_name="Brainstorm Ideas", goal="Birthday party ideas",
                        started_at=day2, completed_at=day2, success=True, user_rating=5, tokens_used=150),
            WorkflowRun(id="run-5", workflow_name="Brainstorm Ideas", goal="Business name ideas",
                        started_at=day3, completed_at=day3, success=True, user_rating=3, tokens_used=120),
            WorkflowRun(id="run-6", workflow_name="Summarize Text", goal="Summarize this article",
                        started_at=day3, completed_at=day3, success=False, tokens_used=90, error="Invalid input"),
        ]
        for run in runs:
            await store.record_run(run)

        return store

    async def test_analyze_empty_db(self, empty_metrics_store, mock_task, mock_context):
        """Test analyzing an empty metrics store."""
        from zebra_tasks.agent.analyzer import MetricsAnalyzerAction

        action = MetricsAnalyzerAction()
        mock_context.extras["__metrics_store__"] = empty_metrics_store

        result = await action.run(mock_task, mock_context)

        assert result.success is True
        analysis = result.output
        assert analysis["total_runs_analyzed"] == 0
        assert analysis["unique_workflows"] == 0
        assert len(analysis["workflow_stats"]) == 0

    async def test_analyze_with_data(self, populated_metrics_store, mock_task, mock_context):
        """Test analyzing a populated metrics store."""
        from zebra_tasks.agent.analyzer import MetricsAnalyzerAction

        action = MetricsAnalyzerAction()
        mock_context.extras["__metrics_store__"] = populated_metrics_store
        mock_task.properties = {"days_to_analyze": 30}

        result = await action.run(mock_task, mock_context)

        assert result.success is True
        analysis = result.output

        assert analysis["total_runs_analyzed"] == 6
        assert analysis["unique_workflows"] == 3
        assert len(analysis["workflow_stats"]) == 3

        # Check workflow stats
        workflow_names = [w["workflow_name"] for w in analysis["workflow_stats"]]
        assert "Answer Question" in workflow_names
        assert "Brainstorm Ideas" in workflow_names

    async def test_analyze_identifies_low_performers(self, populated_metrics_store, mock_task, mock_context):
        """Test that low performers are identified."""
        from zebra_tasks.agent.analyzer import MetricsAnalyzerAction

        action = MetricsAnalyzerAction()
        mock_context.extras["__metrics_store__"] = populated_metrics_store
        mock_task.properties = {"min_runs_for_analysis": 1}

        result = await action.run(mock_task, mock_context)

        assert result.success is True
        low_performers = result.output["low_performers"]

        # Summarize Text has 0% success (1 run, 0 successful)
        low_performer_names = [lp["workflow_name"] for lp in low_performers]
        assert "Summarize Text" in low_performer_names

    async def test_analyze_failure_patterns(self, populated_metrics_store, mock_task, mock_context):
        """Test that failure patterns are identified."""
        from zebra_tasks.agent.analyzer import MetricsAnalyzerAction

        action = MetricsAnalyzerAction()
        mock_context.extras["__metrics_store__"] = populated_metrics_store

        result = await action.run(mock_task, mock_context)

        assert result.success is True
        failure_patterns = result.output["failure_patterns"]

        # Should have patterns for workflows with failures
        assert len(failure_patterns) > 0

    async def test_analyze_generates_recommendations(self, populated_metrics_store, mock_task, mock_context):
        """Test that recommendations are generated."""
        from zebra_tasks.agent.analyzer import MetricsAnalyzerAction

        action = MetricsAnalyzerAction()
        mock_context.extras["__metrics_store__"] = populated_metrics_store
        mock_task.properties = {"min_runs_for_analysis": 1}

        result = await action.run(mock_task, mock_context)

        assert result.success is True
        recommendations = result.output["recommendations"]
        assert len(recommendations) > 0

    async def test_analyze_no_metrics_store(self, mock_task, mock_context):
        """Test error when no metrics store is available."""
        from zebra_tasks.agent.analyzer import MetricsAnalyzerAction

        action = MetricsAnalyzerAction()

        result = await action.run(mock_task, mock_context)

        assert result.success is False
        assert "No metrics store available" in result.error


class TestWorkflowEvaluatorAction:
    """Tests for WorkflowEvaluatorAction."""

    async def test_evaluate_no_metrics(self, mock_task, mock_context):
        """Test error when no metrics provided."""
        from zebra_tasks.agent.evaluator import WorkflowEvaluatorAction

        action = WorkflowEvaluatorAction()
        mock_task.properties = {}

        result = await action.run(mock_task, mock_context)

        assert result.success is False
        assert "No metrics_analysis provided" in result.error

    async def test_evaluate_no_provider(self, mock_task, mock_context):
        """Test error when no LLM provider available."""
        from zebra_tasks.agent.evaluator import WorkflowEvaluatorAction

        action = WorkflowEvaluatorAction()
        mock_task.properties = {
            "metrics_analysis": {"workflow_stats": [], "total_runs_analyzed": 0}
        }

        result = await action.run(mock_task, mock_context)

        assert result.success is False
        assert "No LLM provider available" in result.error

    async def test_evaluate_with_mocked_llm(self, mock_task, mock_context):
        """Test evaluation with mocked LLM."""
        from zebra_tasks.agent.evaluator import WorkflowEvaluatorAction

        action = WorkflowEvaluatorAction()

        # Set up metrics analysis
        metrics_analysis = {
            "analysis_period_days": 7,
            "total_runs_analyzed": 10,
            "unique_workflows": 2,
            "workflow_stats": [
                {"workflow_name": "Test", "total_runs": 10, "success_rate": 0.8, "avg_rating": 4.0}
            ],
            "low_performers": [],
            "failure_patterns": [],
            "recommendations": [],
        }

        mock_task.properties = {
            "metrics_analysis": metrics_analysis,
            "workflow_definitions": {},
        }

        # Mock the LLM response
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "overall_assessment": {
                "health_score": 80,
                "summary": "System is healthy",
                "key_issues": [],
            },
            "workflow_evaluations": [],
            "improvement_priorities": [],
            "new_workflow_suggestions": [],
        })
        mock_response.usage = MagicMock(total_tokens=100)

        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=mock_response)

        mock_context.process.properties["__llm_provider_name__"] = "anthropic"

        with patch("zebra_tasks.llm.providers.registry.get_provider", return_value=mock_provider):
            result = await action.run(mock_task, mock_context)

        assert result.success is True
        evaluation = result.output
        assert evaluation["overall_assessment"]["health_score"] == 80


class TestWorkflowOptimizerAction:
    """Tests for WorkflowOptimizerAction."""

    async def test_optimize_no_evaluation(self, mock_task, mock_context):
        """Test error when no evaluation provided."""
        from zebra_tasks.agent.optimizer import WorkflowOptimizerAction

        action = WorkflowOptimizerAction()
        mock_task.properties = {}

        result = await action.run(mock_task, mock_context)

        assert result.success is False
        assert "No evaluation provided" in result.error

    async def test_optimize_no_provider(self, mock_task, mock_context):
        """Test error when no LLM provider available."""
        from zebra_tasks.agent.optimizer import WorkflowOptimizerAction

        action = WorkflowOptimizerAction()
        mock_task.properties = {
            "evaluation": {"improvement_priorities": [], "new_workflow_suggestions": []}
        }

        result = await action.run(mock_task, mock_context)

        assert result.success is False
        assert "No LLM provider available" in result.error

    async def test_optimize_dry_run(self, temp_dir, mock_task, mock_context):
        """Test optimization in dry-run mode."""
        from zebra_tasks.agent.optimizer import WorkflowOptimizerAction

        action = WorkflowOptimizerAction()

        evaluation = {
            "improvement_priorities": [],
            "new_workflow_suggestions": [
                {
                    "name": "New Test Workflow",
                    "description": "A test workflow",
                    "use_case": "Testing",
                    "rationale": "For testing purposes",
                }
            ],
        }

        mock_task.properties = {
            "evaluation": evaluation,
            "workflow_library_path": str(temp_dir),
            "existing_workflows": {},
            "dry_run": True,
            "max_changes": 1,
        }

        # Mock the LLM response
        mock_response = MagicMock()
        mock_response.content = """name: "New Test Workflow"
description: "A test workflow"
tags: ["test"]
version: 1
first_task: task1
tasks:
  task1:
    name: "Task"
    action: llm_call
    auto: true
    properties:
      prompt: "{{goal}}"
      output_key: result
routings: []"""

        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=mock_response)

        mock_context.process.properties["__llm_provider_name__"] = "anthropic"

        with patch("zebra_tasks.llm.providers.registry.get_provider", return_value=mock_provider):
            result = await action.run(mock_task, mock_context)

        assert result.success is True
        results = result.output

        assert results["dry_run"] is True
        assert len(results["new_workflows"]) == 1
        assert results["new_workflows"][0]["name"] == "New Test Workflow"

        # In dry run, no files should be saved
        yaml_files = list(temp_dir.glob("*.yaml"))
        assert len(yaml_files) == 0

    async def test_optimize_saves_workflow(self, temp_dir, mock_task, mock_context):
        """Test that optimization saves workflows when not in dry-run mode."""
        from zebra_tasks.agent.optimizer import WorkflowOptimizerAction

        action = WorkflowOptimizerAction()

        evaluation = {
            "improvement_priorities": [],
            "new_workflow_suggestions": [
                {
                    "name": "Saved Workflow",
                    "description": "A saved workflow",
                    "use_case": "Testing",
                    "rationale": "For testing purposes",
                }
            ],
        }

        mock_task.properties = {
            "evaluation": evaluation,
            "workflow_library_path": str(temp_dir),
            "existing_workflows": {},
            "dry_run": False,
            "max_changes": 1,
        }

        # Mock the LLM response
        mock_response = MagicMock()
        mock_response.content = """name: "Saved Workflow"
description: "A saved workflow"
tags: ["test"]
version: 1
first_task: task1
tasks:
  task1:
    name: "Task"
    action: llm_call
    auto: true
    properties:
      prompt: "{{goal}}"
      output_key: result
routings: []"""

        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=mock_response)

        mock_context.process.properties["__llm_provider_name__"] = "anthropic"

        with patch("zebra_tasks.llm.providers.registry.get_provider", return_value=mock_provider):
            result = await action.run(mock_task, mock_context)

        assert result.success is True

        # Check that the file was saved
        yaml_files = list(temp_dir.glob("*.yaml"))
        assert len(yaml_files) == 1
        assert "saved_workflow" in yaml_files[0].name

    async def test_optimize_respects_max_changes(self, temp_dir, mock_task, mock_context):
        """Test that max_changes limit is respected."""
        from zebra_tasks.agent.optimizer import WorkflowOptimizerAction

        action = WorkflowOptimizerAction()

        evaluation = {
            "improvement_priorities": [],
            "new_workflow_suggestions": [
                {"name": "Workflow 1", "description": "First", "use_case": "Test", "rationale": "Test"},
                {"name": "Workflow 2", "description": "Second", "use_case": "Test", "rationale": "Test"},
                {"name": "Workflow 3", "description": "Third", "use_case": "Test", "rationale": "Test"},
            ],
        }

        mock_task.properties = {
            "evaluation": evaluation,
            "workflow_library_path": str(temp_dir),
            "existing_workflows": {},
            "dry_run": True,
            "max_changes": 2,
        }

        # Mock the LLM response
        mock_response = MagicMock()
        mock_response.content = """name: "Test"
description: "Test"
tags: []
version: 1
first_task: task1
tasks:
  task1:
    name: "Task"
    action: llm_call
    auto: true
    properties:
      prompt: "{{goal}}"
      output_key: result
routings: []"""

        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=mock_response)

        mock_context.process.properties["__llm_provider_name__"] = "anthropic"

        with patch("zebra_tasks.llm.providers.registry.get_provider", return_value=mock_provider):
            result = await action.run(mock_task, mock_context)

        assert result.success is True
        results = result.output

        # Should only create 2 workflows
        assert len(results["new_workflows"]) == 2
        # Should have skipped 1
        assert len(results["skipped"]) == 1
        assert results["skipped"][0]["reason"] == "max_changes limit reached"
