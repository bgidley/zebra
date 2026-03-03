"""Tests for the agent loop module.

These tests verify the workflow-based agent loop implementation.
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from zebra.core.models import ProcessState

from zebra_agent.library import WorkflowLibrary
from zebra_agent.loop import AgentLoop, AgentResult
from zebra_agent.metrics import WorkflowRun


@pytest.fixture
def temp_dir():
    """Create a temporary directory."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def library_path(temp_dir):
    """Create a library directory."""
    lib_path = temp_dir / "workflows"
    lib_path.mkdir()
    return lib_path


@pytest.fixture
def library(library_path, metrics):
    """Create a WorkflowLibrary instance."""
    return WorkflowLibrary(library_path, metrics)


@pytest.fixture
def agent_main_loop_yaml():
    """The Agent Main Loop workflow YAML."""
    return """name: "Agent Main Loop"
description: "Main agent orchestration loop"
tags: ["agent", "internal", "system"]
use_when: "INTERNAL USE ONLY"
version: 1
first_task: check_memory

tasks:
  check_memory:
    name: "Check Memory Status"
    action: memory_check
    auto: true
    properties:
      output_key: memory_status

  select_workflow:
    name: "Select Workflow"
    action: workflow_selector
    auto: true
    properties:
      goal: "{{goal}}"
      available_workflows: "{{available_workflows}}"
      output_key: selection

  execute_workflow:
    name: "Execute Workflow"
    action: execute_goal_workflow
    auto: true
    properties:
      workflow_name: "{{workflow_name}}"
      goal: "{{goal}}"
      output_key: execution_result

routings:
  - from: check_memory
    to: select_workflow
    condition: route_name
    name: "continue"

  - from: select_workflow
    to: execute_workflow
    condition: route_name
    name: "use_existing"
"""


@pytest.fixture
def sample_workflow_yaml():
    """Sample workflow YAML content."""
    return """name: "Test Workflow"
description: "A test workflow"
tags: ["test"]
version: 1
first_task: task1

tasks:
  task1:
    name: "Test Task"
    action: llm_call
    auto: true
    properties:
      prompt: "{{goal}}"
      output_key: answer

routings: []
"""


@pytest.fixture
def mock_engine():
    """Create a mock workflow engine."""
    engine = MagicMock()
    engine.store = MagicMock()
    engine.extras = {}  # For engine-level dependency injection
    return engine


class TestAgentResult:
    """Tests for AgentResult dataclass."""

    def test_create_result(self):
        """Test creating an agent result."""
        result = AgentResult(
            run_id="test-id",
            workflow_name="TestWorkflow",
            goal="Test goal",
            output="Test output",
            success=True,
            tokens_used=100,
        )
        assert result.run_id == "test-id"
        assert result.workflow_name == "TestWorkflow"
        assert result.success is True
        assert result.tokens_used == 100

    def test_result_with_error(self):
        """Test result with error."""
        result = AgentResult(
            run_id="test-id",
            workflow_name="TestWorkflow",
            goal="Test goal",
            output=None,
            success=False,
            error="Something went wrong",
        )
        assert result.success is False
        assert result.error == "Something went wrong"

    def test_result_created_new_workflow(self):
        """Test result indicating new workflow creation."""
        result = AgentResult(
            run_id="test-id",
            workflow_name="NewWorkflow",
            goal="Test goal",
            output="Test output",
            success=True,
            created_new_workflow=True,
        )
        assert result.created_new_workflow is True


class TestAgentLoopInitialization:
    """Tests for AgentLoop initialization."""

    def test_initialization(self, library, mock_engine, metrics):
        """Test agent loop initialization."""
        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )
        assert loop.library is library
        assert loop.engine is mock_engine
        assert loop.metrics is metrics
        assert loop.provider_name == "anthropic"

    def test_initialization_with_memory(self, library, mock_engine, metrics, memory):
        """Test initialization with memory."""
        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            memory=memory,
            provider="anthropic",
        )
        assert loop.memory is memory

    def test_initialization_with_model(self, library, mock_engine, metrics):
        """Test initialization with custom model."""
        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
            model="claude-3-opus",
        )
        assert loop.model == "claude-3-opus"


class TestIsSystemWorkflow:
    """Tests for _is_system_workflow method."""

    def test_agent_main_loop_is_system(self, library, mock_engine, metrics):
        """Test that Agent Main Loop is identified as system workflow."""
        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )
        assert loop._is_system_workflow("Agent Main Loop") is True

    def test_memory_compact_not_system(self, library, mock_engine, metrics):
        """Test that old memory compact workflows are no longer system workflows.

        The compaction step was removed in the new loop design; compaction
        is now replaced by the incremental conceptual memory update.
        """
        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )
        assert loop._is_system_workflow("Memory Compact Short") is False
        assert loop._is_system_workflow("Memory Compact Long") is False

    def test_regular_workflow_not_system(self, library, mock_engine, metrics):
        """Test that regular workflows are not system workflows."""
        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )
        assert loop._is_system_workflow("Test Workflow") is False
        assert loop._is_system_workflow("Code Review") is False


class TestRecordRating:
    """Tests for recording ratings."""

    async def test_record_rating(self, library, mock_engine, metrics):
        """Test recording a rating."""
        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )

        run = WorkflowRun.create("TestWorkflow", "Test goal")
        await metrics.record_run(run)

        await loop.record_rating(run.id, 5)

        retrieved = await metrics.get_run(run.id)
        assert retrieved.user_rating == 5


class TestProcessGoalWorkflowNotFound:
    """Tests for process_goal when Agent Main Loop workflow is missing."""

    async def test_process_goal_raises_when_workflow_missing(self, library, mock_engine, metrics):
        """Test that process_goal raises ValueError when workflow is missing."""
        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )

        with pytest.raises(ValueError, match="Workflow not found"):
            await loop.process_goal("Test goal")


class TestProcessGoalSuccess:
    """Tests for successful goal processing."""

    async def test_process_goal_success(
        self, library, mock_engine, metrics, agent_main_loop_yaml, sample_workflow_yaml
    ):
        """Test successful goal processing through workflow."""
        # Create the workflows
        (library.library_path / "agent_main_loop.yaml").write_text(agent_main_loop_yaml)
        (library.library_path / "test.yaml").write_text(sample_workflow_yaml)

        # Setup mock engine for successful completion
        mock_process = MagicMock()
        mock_process.id = "process-1"
        mock_process.state = ProcessState.COMPLETE
        mock_process.properties = {
            "workflow_name": "Test Workflow",
            "execution_result": {
                "success": True,
                "output": "Test answer",
                "tokens_used": 50,
            },
            "created_new": False,
        }

        mock_engine.create_process = AsyncMock(return_value=mock_process)
        mock_engine.start_process = AsyncMock()
        mock_engine.store.load_process = AsyncMock(return_value=mock_process)

        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )

        result = await loop.process_goal("Test goal")

        assert result.success is True
        assert result.workflow_name == "Test Workflow"
        assert result.output == "Test answer"
        assert result.tokens_used == 50
        assert result.created_new_workflow is False


class TestProcessGoalFailure:
    """Tests for failed goal processing."""

    async def test_process_goal_workflow_failed(
        self, library, mock_engine, metrics, agent_main_loop_yaml
    ):
        """Test goal processing when workflow fails."""
        (library.library_path / "agent_main_loop.yaml").write_text(agent_main_loop_yaml)

        # Setup mock engine for failure
        mock_process = MagicMock()
        mock_process.id = "process-1"
        mock_process.state = ProcessState.FAILED
        mock_process.properties = {
            "workflow_name": "Test Workflow",
            "__error__": "Task execution failed",
            "created_new": False,
        }

        mock_engine.create_process = AsyncMock(return_value=mock_process)
        mock_engine.start_process = AsyncMock()
        mock_engine.store.load_process = AsyncMock(return_value=mock_process)

        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )

        result = await loop.process_goal("Test goal")

        assert result.success is False
        assert "Task execution failed" in result.error

    async def test_process_goal_timeout(self, library, mock_engine, metrics, agent_main_loop_yaml):
        """Test goal processing timeout."""
        (library.library_path / "agent_main_loop.yaml").write_text(agent_main_loop_yaml)

        # Setup mock engine to keep running (timeout)
        mock_process = MagicMock()
        mock_process.id = "process-1"
        mock_process.state = ProcessState.RUNNING
        mock_process.properties = {"workflow_name": "unknown"}

        mock_engine.create_process = AsyncMock(return_value=mock_process)
        mock_engine.start_process = AsyncMock()
        mock_engine.store.load_process = AsyncMock(return_value=mock_process)

        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )

        import asyncio

        with patch.object(asyncio, "sleep", new_callable=AsyncMock):
            result = await loop.process_goal("Test goal")

        assert result.success is False
        assert "timed out" in result.error


class TestProcessGoalWithProgressCallback:
    """Tests for process_goal with progress callback."""

    async def test_process_goal_emits_started_event(
        self, library, mock_engine, metrics, agent_main_loop_yaml
    ):
        """Test that process_goal emits started event."""
        (library.library_path / "agent_main_loop.yaml").write_text(agent_main_loop_yaml)

        mock_process = MagicMock()
        mock_process.id = "process-1"
        mock_process.state = ProcessState.COMPLETE
        mock_process.properties = {
            "workflow_name": "Test",
            "execution_result": {"success": True, "output": "Done", "tokens_used": 10},
        }

        mock_engine.create_process = AsyncMock(return_value=mock_process)
        mock_engine.start_process = AsyncMock()
        mock_engine.store.load_process = AsyncMock(return_value=mock_process)

        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )

        events = []

        async def callback(event: str, data: dict):
            events.append((event, data))

        await loop.process_goal("Test goal", progress_callback=callback)

        assert len(events) == 1
        assert events[0][0] == "started"
        assert "run_id" in events[0][1]
        assert events[0][1]["goal"] == "Test goal"


class TestProcessGoalWithRunId:
    """Tests for process_goal with custom run_id."""

    async def test_process_goal_uses_provided_run_id(
        self, library, mock_engine, metrics, agent_main_loop_yaml
    ):
        """Test that process_goal uses provided run_id."""
        (library.library_path / "agent_main_loop.yaml").write_text(agent_main_loop_yaml)

        mock_process = MagicMock()
        mock_process.id = "process-1"
        mock_process.state = ProcessState.COMPLETE
        mock_process.properties = {
            "workflow_name": "Test",
            "execution_result": {"success": True, "output": "Done", "tokens_used": 10},
        }

        mock_engine.create_process = AsyncMock(return_value=mock_process)
        mock_engine.start_process = AsyncMock()
        mock_engine.store.load_process = AsyncMock(return_value=mock_process)

        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )

        result = await loop.process_goal("Test goal", run_id="custom-run-id")

        assert result.run_id == "custom-run-id"


class TestProcessGoalPassesStores:
    """Tests that process_goal passes stores to workflow via engine.extras."""

    async def test_process_goal_passes_stores_in_engine_extras(
        self, library, mock_engine, metrics, memory, agent_main_loop_yaml
    ):
        """Test that stores are passed in engine.extras (not process properties)."""
        (library.library_path / "agent_main_loop.yaml").write_text(agent_main_loop_yaml)

        captured_properties = {}

        async def capture_create_process(definition, properties=None):
            captured_properties.update(properties or {})
            mock_process = MagicMock()
            mock_process.id = "process-1"
            mock_process.state = ProcessState.COMPLETE
            mock_process.properties = {
                "workflow_name": "Test",
                "execution_result": {"success": True, "output": "Done", "tokens_used": 10},
            }
            return mock_process

        mock_engine.create_process = AsyncMock(side_effect=capture_create_process)
        mock_engine.start_process = AsyncMock()

        mock_process = MagicMock()
        mock_process.state = ProcessState.COMPLETE
        mock_process.properties = {
            "workflow_name": "Test",
            "execution_result": {"success": True, "output": "Done", "tokens_used": 10},
        }
        mock_engine.store.load_process = AsyncMock(return_value=mock_process)

        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            memory=memory,
            provider="anthropic",
        )

        await loop.process_goal("Test goal")

        # Verify stores are NOT in process properties (they're not JSON-serializable)
        assert "__memory_store__" not in captured_properties
        assert "__metrics_store__" not in captured_properties
        assert "__workflow_library__" not in captured_properties

        # Verify stores ARE in engine.extras
        assert mock_engine.extras.get("__memory_store__") is memory
        assert mock_engine.extras.get("__metrics_store__") is metrics
        assert mock_engine.extras.get("__workflow_library__") is library

        # Verify regular properties are still passed
        assert captured_properties.get("goal") == "Test goal"
        assert "__llm_provider_name__" in captured_properties


class TestProcessGoalFiltersSystemWorkflows:
    """Tests that system workflows are filtered from available_workflows."""

    async def test_process_goal_excludes_system_workflows(
        self, library, mock_engine, metrics, agent_main_loop_yaml, sample_workflow_yaml
    ):
        """Test that system workflows are excluded from available_workflows."""
        # Create both system and regular workflows
        (library.library_path / "agent_main_loop.yaml").write_text(agent_main_loop_yaml)
        (library.library_path / "test.yaml").write_text(sample_workflow_yaml)

        # Create memory compact workflow
        compact_yaml = """name: "Memory Compact Short"
description: "Compact memory"
tags: ["internal"]
version: 1
first_task: task1
tasks:
  task1:
    name: "Task"
    action: llm_call
    auto: true
    properties:
      prompt: "test"
      output_key: result
routings: []
"""
        (library.library_path / "compact.yaml").write_text(compact_yaml)

        captured_properties = {}

        async def capture_create_process(definition, properties=None):
            captured_properties.update(properties or {})
            mock_process = MagicMock()
            mock_process.id = "process-1"
            mock_process.state = ProcessState.COMPLETE
            mock_process.properties = {
                "workflow_name": "Test Workflow",
                "execution_result": {"success": True, "output": "Done", "tokens_used": 10},
            }
            return mock_process

        mock_engine.create_process = AsyncMock(side_effect=capture_create_process)
        mock_engine.start_process = AsyncMock()

        mock_process = MagicMock()
        mock_process.state = ProcessState.COMPLETE
        mock_process.properties = {
            "workflow_name": "Test Workflow",
            "execution_result": {"success": True, "output": "Done", "tokens_used": 10},
        }
        mock_engine.store.load_process = AsyncMock(return_value=mock_process)

        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )

        await loop.process_goal("Test goal")

        # Verify system workflows were excluded
        available = captured_properties.get("available_workflows", [])
        names = [w["name"] for w in available]

        assert "Test Workflow" in names
        assert "Agent Main Loop" not in names
        # Memory Compact Short/Long are no longer system workflows in the new design
        # (the compaction step is replaced by incremental conceptual memory updates)
        assert "Memory Compact Short" in names
