"""Tests for the loop module."""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from zebra.core.models import ProcessState

from zebra_agent.library import WorkflowLibrary
from zebra_agent.loop import AgentLoop, AgentResult, WorkflowSelection
from zebra_agent.memory import AgentMemory, MemoryEntry, ShortTermSummary, LongTermTheme
from zebra_agent.metrics import MetricsStore, WorkflowRun


@pytest.fixture
def temp_dir():
    """Create a temporary directory."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def temp_db(temp_dir):
    """Create a temporary database file."""
    return temp_dir / "metrics.db"


@pytest.fixture
def metrics(temp_db):
    """Create a MetricsStore instance."""
    return MetricsStore(temp_db)


@pytest.fixture
def memory_db(temp_dir):
    """Create a temporary memory database file."""
    return temp_dir / "memory.db"


@pytest.fixture
def memory(memory_db):
    """Create an AgentMemory instance."""
    return AgentMemory(memory_db, short_term_max_tokens=1000, long_term_max_tokens=2000)


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


class TestWorkflowSelection:
    """Tests for WorkflowSelection dataclass."""

    def test_create_selection(self):
        """Test creating a workflow selection."""
        selection = WorkflowSelection(
            workflow_name="TestWorkflow",
            create_new=False,
            reasoning="This workflow matches the goal",
        )
        assert selection.workflow_name == "TestWorkflow"
        assert selection.create_new is False

    def test_selection_create_new(self):
        """Test selection for creating new workflow."""
        selection = WorkflowSelection(
            workflow_name=None,
            create_new=True,
            reasoning="No matching workflow found",
            suggested_name="New Workflow",
        )
        assert selection.workflow_name is None
        assert selection.create_new is True
        assert selection.suggested_name == "New Workflow"


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
        assert loop._llm is None

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


class TestLLMProperty:
    """Tests for lazy LLM initialization."""

    def test_llm_lazy_initialization(self, library, mock_engine, metrics):
        """Test that LLM is lazily initialized."""
        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )
        assert loop._llm is None

        with patch("zebra_agent.loop.get_provider") as mock_get:
            mock_get.return_value = MagicMock()
            _ = loop.llm
            mock_get.assert_called_once_with("anthropic", None)
            assert loop._llm is not None

    def test_llm_cached(self, library, mock_engine, metrics):
        """Test that LLM is cached after initialization."""
        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )

        with patch("zebra_agent.loop.get_provider") as mock_get:
            mock_provider = MagicMock()
            mock_get.return_value = mock_provider

            llm1 = loop.llm
            llm2 = loop.llm

            # Should only call get_provider once
            mock_get.assert_called_once()
            assert llm1 is llm2


class TestSelectWorkflow:
    """Tests for workflow selection."""

    async def test_select_workflow_existing(self, library, mock_engine, metrics, sample_workflow_yaml):
        """Test selecting an existing workflow."""
        (library.library_path / "test.yaml").write_text(sample_workflow_yaml)

        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )

        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "workflow_name": "Test Workflow",
            "create_new": False,
            "reasoning": "This workflow matches the goal",
        })

        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(return_value=mock_response)
        loop._llm = mock_llm

        selection = await loop._select_workflow("Test goal")

        assert selection.workflow_name == "Test Workflow"
        assert selection.create_new is False

    async def test_select_workflow_create_new(self, library, mock_engine, metrics):
        """Test selecting to create a new workflow."""
        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )

        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "workflow_name": None,
            "create_new": True,
            "reasoning": "No matching workflow",
            "suggested_name": "New Workflow",
        })

        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(return_value=mock_response)
        loop._llm = mock_llm

        selection = await loop._select_workflow("Unique goal")

        assert selection.create_new is True
        assert selection.suggested_name == "New Workflow"

    async def test_select_workflow_no_workflows_forces_create(self, library, mock_engine, metrics):
        """Test that no workflows forces create_new."""
        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )

        mock_response = MagicMock()
        # Even if LLM says don't create, should force create when no workflows
        mock_response.content = json.dumps({
            "workflow_name": "Test",
            "create_new": False,
            "reasoning": "Test",
        })

        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(return_value=mock_response)
        loop._llm = mock_llm

        selection = await loop._select_workflow("Test goal")

        assert selection.create_new is True
        assert selection.workflow_name is None

    async def test_select_workflow_json_in_code_block(self, library, mock_engine, metrics, sample_workflow_yaml):
        """Test parsing JSON from code block."""
        (library.library_path / "test.yaml").write_text(sample_workflow_yaml)

        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )

        mock_response = MagicMock()
        mock_response.content = """```json
{
    "workflow_name": "Test Workflow",
    "create_new": false,
    "reasoning": "Matches"
}
```"""

        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(return_value=mock_response)
        loop._llm = mock_llm

        selection = await loop._select_workflow("Test goal")

        assert selection.workflow_name == "Test Workflow"


class TestCreateWorkflow:
    """Tests for workflow creation."""

    async def test_create_workflow(self, library, mock_engine, metrics):
        """Test creating a new workflow."""
        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )

        yaml_content = """name: "New Workflow"
description: "A new workflow"
tags: ["new"]
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
routings: []
"""
        mock_response = MagicMock()
        mock_response.content = yaml_content

        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(return_value=mock_response)
        loop._llm = mock_llm

        name = await loop._create_workflow("Create something", "New Workflow")

        assert name == "New Workflow"
        assert (library.library_path / "new_workflow.yaml").exists()

    async def test_create_workflow_strips_yaml_code_block(self, library, mock_engine, metrics):
        """Test that YAML code blocks are stripped."""
        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )

        yaml_content = """```yaml
name: "New Workflow"
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
routings: []
```"""
        mock_response = MagicMock()
        mock_response.content = yaml_content

        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(return_value=mock_response)
        loop._llm = mock_llm

        name = await loop._create_workflow("Create something", None)

        assert name == "New Workflow"


class TestAddToMemory:
    """Tests for adding to memory."""

    async def test_add_to_memory(self, library, mock_engine, metrics, memory):
        """Test adding a run to memory."""
        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            memory=memory,
            provider="anthropic",
        )

        run = WorkflowRun.create("TestWorkflow", "Test goal")
        run.started_at = datetime.now()

        await loop._add_to_memory(run, "Test output")

        entries = await memory.get_short_term_entries()
        assert len(entries) == 1
        assert entries[0].goal == "Test goal"

    async def test_add_to_memory_dict_output(self, library, mock_engine, metrics, memory):
        """Test adding with dict output."""
        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            memory=memory,
            provider="anthropic",
        )

        run = WorkflowRun.create("TestWorkflow", "Test goal")
        run.started_at = datetime.now()

        await loop._add_to_memory(run, {"key": "value"})

        entries = await memory.get_short_term_entries()
        assert len(entries) == 1
        assert "key" in entries[0].result_summary

    async def test_add_to_memory_no_memory(self, library, mock_engine, metrics):
        """Test adding when no memory configured."""
        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )

        run = WorkflowRun.create("TestWorkflow", "Test goal")
        # Should not raise
        await loop._add_to_memory(run, "Test output")

    async def test_add_to_memory_truncates_long_output(self, library, mock_engine, metrics, memory):
        """Test that long output is truncated."""
        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            memory=memory,
            provider="anthropic",
        )

        run = WorkflowRun.create("TestWorkflow", "Test goal")
        run.started_at = datetime.now()

        long_output = "x" * 1000
        await loop._add_to_memory(run, long_output)

        entries = await memory.get_short_term_entries()
        assert len(entries[0].result_summary) <= 503  # 500 + "..."


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


class TestCompactShortTermMemory:
    """Tests for short-term memory compaction."""

    async def test_compact_short_term_no_memory(self, library, mock_engine, metrics):
        """Test compaction with no memory configured."""
        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )

        # Should not raise
        await loop._compact_short_term_memory()

    async def test_compact_short_term_no_workflow(self, library, mock_engine, metrics, memory):
        """Test compaction when workflow doesn't exist."""
        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            memory=memory,
            provider="anthropic",
        )

        # Add some entries
        entry = MemoryEntry(
            id="test",
            timestamp=datetime.now(),
            goal="Test",
            workflow_used="Test",
            result_summary="Test",
            tokens=100,
        )
        await memory.add_entry(entry)

        # Should not raise even without workflow (silently skips)
        await loop._compact_short_term_memory()

        # Entries should still be there since workflow didn't exist
        entries = await memory.get_short_term_entries()
        assert len(entries) == 1

    async def test_compact_short_term_empty_content(self, library, mock_engine, metrics, memory):
        """Test compaction with empty memory content."""
        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            memory=memory,
            provider="anthropic",
        )

        # Should not raise with empty memory
        await loop._compact_short_term_memory()


class TestCompactLongTermMemory:
    """Tests for long-term memory compaction."""

    async def test_compact_long_term_no_memory(self, library, mock_engine, metrics):
        """Test compaction with no memory configured."""
        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )

        # Should not raise
        await loop._compact_long_term_memory()

    async def test_compact_long_term_no_workflow(self, library, mock_engine, metrics, memory):
        """Test compaction when workflow doesn't exist."""
        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            memory=memory,
            provider="anthropic",
        )

        # Add some summaries
        summary = ShortTermSummary(
            id="sum-1",
            created_at=datetime.now(),
            summary="Test summary",
            tokens=100,
            entry_count=5,
        )
        await memory.add_short_term_summary(summary)

        # Should not raise even without workflow (silently skips)
        await loop._compact_long_term_memory()

        # Summary should still be there since workflow didn't exist
        summaries = await memory.get_short_term_summaries()
        assert len(summaries) == 1

    async def test_compact_long_term_empty_content(self, library, mock_engine, metrics, memory):
        """Test compaction with empty memory content."""
        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            memory=memory,
            provider="anthropic",
        )

        # Should not raise with empty memory
        await loop._compact_long_term_memory()


class TestSelectWorkflowWithUseWhen:
    """Tests for workflow selection with use_when field."""

    async def test_select_workflow_includes_use_when(self, library, mock_engine, metrics):
        """Test that use_when field is included in selection prompt."""
        yaml_content = """name: "Test Workflow"
description: "A test workflow"
tags: ["test"]
use_when: "Use this when the user asks about testing"
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
        (library.library_path / "test.yaml").write_text(yaml_content)

        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )

        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "workflow_name": "Test Workflow",
            "create_new": False,
            "reasoning": "Matches use_when",
        })

        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(return_value=mock_response)
        loop._llm = mock_llm

        await loop._select_workflow("Test goal")

        # Check that the LLM was called with use_when in the prompt
        call_args = mock_llm.complete.call_args
        messages = call_args.kwargs["messages"]
        user_message = messages[1].content
        assert "USE WHEN" in user_message


class TestSelectWorkflowCodeBlockParsing:
    """Tests for JSON parsing from various code block formats."""

    async def test_select_workflow_plain_code_block(self, library, mock_engine, metrics, sample_workflow_yaml):
        """Test parsing JSON from plain code block (no language specifier)."""
        (library.library_path / "test.yaml").write_text(sample_workflow_yaml)

        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )

        mock_response = MagicMock()
        mock_response.content = """Here's my selection:
```
{
    "workflow_name": "Test Workflow",
    "create_new": false,
    "reasoning": "Matches"
}
```
That's my choice."""

        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(return_value=mock_response)
        loop._llm = mock_llm

        selection = await loop._select_workflow("Test goal")

        assert selection.workflow_name == "Test Workflow"


class TestCreateWorkflowCodeBlockParsing:
    """Tests for YAML parsing from various code block formats."""

    async def test_create_workflow_yml_code_block(self, library, mock_engine, metrics):
        """Test parsing YAML from yml code block."""
        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )

        yaml_content = """```yml
name: "New Workflow"
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
routings: []
```"""
        mock_response = MagicMock()
        mock_response.content = yaml_content

        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(return_value=mock_response)
        loop._llm = mock_llm

        name = await loop._create_workflow("Create something", None)

        assert name == "New Workflow"

    async def test_create_workflow_plain_code_block(self, library, mock_engine, metrics):
        """Test parsing YAML from plain code block."""
        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )

        yaml_content = """Here's the workflow:
```
name: "New Workflow"
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
routings: []
```
That should work."""
        mock_response = MagicMock()
        mock_response.content = yaml_content

        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(return_value=mock_response)
        loop._llm = mock_llm

        name = await loop._create_workflow("Create something", None)

        assert name == "New Workflow"


class TestExecuteWorkflowOutputKeys:
    """Tests for workflow execution with various output keys."""

    async def test_execute_workflow_summary_key(self, library, mock_engine, metrics, sample_workflow_yaml):
        """Test execution with summary output key."""
        yaml_content = """name: "Summary Workflow"
description: "A workflow that outputs summary"
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
      output_key: summary
routings: []
"""
        (library.library_path / "summary.yaml").write_text(yaml_content)

        mock_process = MagicMock()
        mock_process.id = "process-1"
        mock_process.state = ProcessState.COMPLETE
        mock_process.properties = {"summary": "Test summary", "__total_tokens__": 50}

        mock_engine.create_process = AsyncMock(return_value=mock_process)
        mock_engine.start_process = AsyncMock()
        mock_engine.store.load_process = AsyncMock(return_value=mock_process)

        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )

        output, tokens = await loop._execute_workflow("Summary Workflow", "Test goal")

        assert output == "Test summary"
        assert tokens == 50

    async def test_execute_workflow_fallback_to_properties(self, library, mock_engine, metrics, sample_workflow_yaml):
        """Test execution falls back to all properties when no standard key."""
        yaml_content = """name: "Custom Workflow"
description: "A workflow with custom output"
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
      output_key: custom_output
routings: []
"""
        (library.library_path / "custom.yaml").write_text(yaml_content)

        mock_process = MagicMock()
        mock_process.id = "process-1"
        mock_process.state = ProcessState.COMPLETE
        mock_process.properties = {
            "custom_output": "Test output",
            "goal": "Test goal",
            "__total_tokens__": 50,
            "__llm_provider_name__": "anthropic",
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

        output, tokens = await loop._execute_workflow("Custom Workflow", "Test goal")

        # Should fall back to non-private properties
        assert isinstance(output, dict)
        assert "custom_output" in output
        assert "goal" in output
        assert "__total_tokens__" not in output


class TestProcessGoalWithMemoryCompaction:
    """Tests for process_goal with memory compaction triggers."""

    async def test_process_goal_triggers_short_term_compaction(
        self, library, mock_engine, metrics, memory, sample_workflow_yaml
    ):
        """Test that process_goal triggers short-term compaction when needed."""
        (library.library_path / "test.yaml").write_text(sample_workflow_yaml)

        # Add enough entries to trigger compaction (90% of 1000 = 900 tokens)
        entry = MemoryEntry(
            id="test",
            timestamp=datetime.now(),
            goal="Test",
            workflow_used="Test",
            result_summary="Test",
            tokens=950,  # Over threshold
        )
        await memory.add_entry(entry)

        mock_process = MagicMock()
        mock_process.id = "process-1"
        mock_process.state = ProcessState.COMPLETE
        mock_process.properties = {"answer": "Result", "__total_tokens__": 50}

        mock_engine.create_process = AsyncMock(return_value=mock_process)
        mock_engine.start_process = AsyncMock()
        mock_engine.store.load_process = AsyncMock(return_value=mock_process)

        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            memory=memory,
            provider="anthropic",
        )

        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "workflow_name": "Test Workflow",
            "create_new": False,
            "reasoning": "Matches",
        })

        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(return_value=mock_response)
        loop._llm = mock_llm

        # This should attempt compaction but workflow doesn't exist
        # It should still complete successfully
        result = await loop.process_goal("Test goal")

        assert result.success is True


class TestProcessGoalIntegration:
    """Integration tests for process_goal (with mocked externals)."""

    async def test_process_goal_success(self, library, mock_engine, metrics, sample_workflow_yaml):
        """Test successful goal processing."""
        (library.library_path / "test.yaml").write_text(sample_workflow_yaml)

        # Setup mock engine
        mock_process = MagicMock()
        mock_process.id = "process-1"
        mock_process.state = ProcessState.COMPLETE
        mock_process.properties = {"answer": "Test answer", "__total_tokens__": 50}
        mock_process.error = None

        mock_engine.create_process = AsyncMock(return_value=mock_process)
        mock_engine.start_process = AsyncMock()
        mock_engine.store.load_process = AsyncMock(return_value=mock_process)

        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )

        # Mock LLM for selection
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "workflow_name": "Test Workflow",
            "create_new": False,
            "reasoning": "Matches",
        })

        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(return_value=mock_response)
        loop._llm = mock_llm

        result = await loop.process_goal("Test goal")

        assert result.success is True
        assert result.workflow_name == "Test Workflow"
        assert result.output == "Test answer"

    async def test_process_goal_creates_new_workflow(self, library, mock_engine, metrics):
        """Test goal processing that creates new workflow."""
        # Setup mock engine
        mock_process = MagicMock()
        mock_process.id = "process-1"
        mock_process.state = ProcessState.COMPLETE
        mock_process.properties = {"result": "Done", "__total_tokens__": 100}
        mock_process.error = None

        mock_engine.create_process = AsyncMock(return_value=mock_process)
        mock_engine.start_process = AsyncMock()
        mock_engine.store.load_process = AsyncMock(return_value=mock_process)

        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )

        # Mock LLM responses
        selector_response = MagicMock()
        selector_response.content = json.dumps({
            "workflow_name": None,
            "create_new": True,
            "reasoning": "No match",
            "suggested_name": "New Workflow",
        })

        creator_response = MagicMock()
        creator_response.content = """name: "New Workflow"
description: "Created"
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
routings: []
"""

        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(side_effect=[selector_response, creator_response])
        loop._llm = mock_llm

        result = await loop.process_goal("Unique goal")

        assert result.success is True
        assert result.created_new_workflow is True

    async def test_process_goal_failure(self, library, mock_engine, metrics, sample_workflow_yaml):
        """Test goal processing with failure."""
        (library.library_path / "test.yaml").write_text(sample_workflow_yaml)

        # Setup mock engine to fail
        mock_process = MagicMock()
        mock_process.id = "process-1"
        mock_process.state = ProcessState.FAILED
        mock_process.error = "Workflow error"

        mock_engine.create_process = AsyncMock(return_value=mock_process)
        mock_engine.start_process = AsyncMock()
        mock_engine.store.load_process = AsyncMock(return_value=mock_process)

        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )

        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "workflow_name": "Test Workflow",
            "create_new": False,
            "reasoning": "Matches",
        })

        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(return_value=mock_response)
        loop._llm = mock_llm

        result = await loop.process_goal("Test goal")

        assert result.success is False
        assert "Workflow error" in result.error

    async def test_process_goal_with_memory(self, library, mock_engine, metrics, memory, sample_workflow_yaml):
        """Test goal processing updates memory."""
        (library.library_path / "test.yaml").write_text(sample_workflow_yaml)

        mock_process = MagicMock()
        mock_process.id = "process-1"
        mock_process.state = ProcessState.COMPLETE
        mock_process.properties = {"answer": "Result", "__total_tokens__": 50}

        mock_engine.create_process = AsyncMock(return_value=mock_process)
        mock_engine.start_process = AsyncMock()
        mock_engine.store.load_process = AsyncMock(return_value=mock_process)

        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            memory=memory,
            provider="anthropic",
        )

        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "workflow_name": "Test Workflow",
            "create_new": False,
            "reasoning": "Matches",
        })

        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(return_value=mock_response)
        loop._llm = mock_llm

        await loop.process_goal("Test goal")

        # Check memory was updated
        entries = await memory.get_short_term_entries()
        assert len(entries) == 1
        assert entries[0].goal == "Test goal"


class TestProcessGoalFailureWithMemory:
    """Tests for process_goal failure paths with memory."""

    async def test_process_goal_failure_updates_memory(
        self, library, mock_engine, metrics, memory, sample_workflow_yaml
    ):
        """Test that failed goal processing still updates memory."""
        (library.library_path / "test.yaml").write_text(sample_workflow_yaml)

        mock_process = MagicMock()
        mock_process.id = "process-1"
        mock_process.state = ProcessState.FAILED
        mock_process.error = "Test error"

        mock_engine.create_process = AsyncMock(return_value=mock_process)
        mock_engine.start_process = AsyncMock()
        mock_engine.store.load_process = AsyncMock(return_value=mock_process)

        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            memory=memory,
            provider="anthropic",
        )

        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "workflow_name": "Test Workflow",
            "create_new": False,
            "reasoning": "Matches",
        })

        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(return_value=mock_response)
        loop._llm = mock_llm

        result = await loop.process_goal("Test goal")

        assert result.success is False

        # Check memory was still updated with error
        entries = await memory.get_short_term_entries()
        assert len(entries) == 1
        assert "Error" in entries[0].result_summary


class TestCreateWorkflowWithExistingWorkflows:
    """Tests for workflow creation with existing workflows for reference."""

    async def test_create_workflow_includes_existing_for_reference(self, library, mock_engine, metrics):
        """Test that existing workflows are included for reference."""
        # Create some existing workflows
        for i in range(2):
            yaml_content = f"""name: "Existing Workflow {i}"
description: "Description {i}"
tags: []
version: 1
first_task: task1
tasks:
  task1:
    name: "Task"
    action: llm_call
    auto: true
    properties:
      prompt: "{{{{goal}}}}"
      output_key: result
routings: []
"""
            (library.library_path / f"existing_{i}.yaml").write_text(yaml_content)

        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )

        yaml_content = """name: "New Workflow"
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
routings: []
"""
        mock_response = MagicMock()
        mock_response.content = yaml_content

        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(return_value=mock_response)
        loop._llm = mock_llm

        await loop._create_workflow("Create something", "New Workflow")

        # Verify the prompt included existing workflows
        call_args = mock_llm.complete.call_args
        messages = call_args.kwargs["messages"]
        user_message = messages[1].content
        assert "Existing workflows for reference" in user_message
        assert "Existing Workflow 0" in user_message


class TestExecuteWorkflowTimeout:
    """Tests for workflow execution timeout."""

    async def test_execute_workflow_timeout(self, library, mock_engine, metrics, sample_workflow_yaml):
        """Test that workflow execution times out."""
        (library.library_path / "test.yaml").write_text(sample_workflow_yaml)

        call_count = [0]

        def make_mock_process(process_id):
            mock_process = MagicMock()
            mock_process.id = process_id
            # Return RUNNING state until we've been called many times
            call_count[0] += 1
            if call_count[0] < 250:  # max_wait is 120, sleep 0.5 = 240 calls max
                mock_process.state = ProcessState.RUNNING
            else:
                # Never gets here in normal test since we'll timeout first
                mock_process.state = ProcessState.COMPLETE
            mock_process.error = None
            mock_process.properties = {}
            return mock_process

        initial_process = MagicMock()
        initial_process.id = "process-1"
        initial_process.state = ProcessState.RUNNING

        mock_engine.create_process = AsyncMock(return_value=initial_process)
        mock_engine.start_process = AsyncMock()
        mock_engine.store.load_process = AsyncMock(side_effect=make_mock_process)

        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            provider="anthropic",
        )

        # Patch asyncio.sleep to speed up the test
        import asyncio
        with patch.object(asyncio, "sleep", new_callable=AsyncMock):
            with pytest.raises(RuntimeError, match="timed out"):
                await loop._execute_workflow("Test Workflow", "Test goal")


class TestProcessGoalWithLongTermCompaction:
    """Tests for long-term memory compaction triggers."""

    async def test_process_goal_triggers_long_term_compaction(
        self, library, mock_engine, metrics, memory, sample_workflow_yaml
    ):
        """Test that process_goal triggers long-term compaction when needed."""
        (library.library_path / "test.yaml").write_text(sample_workflow_yaml)

        # Add enough to trigger long-term compaction (90% of 2000 = 1800)
        summary = ShortTermSummary(
            id="sum-1",
            created_at=datetime.now(),
            summary="Test summary",
            tokens=1000,
            entry_count=10,
        )
        await memory.add_short_term_summary(summary)

        theme = LongTermTheme(
            id="theme-1",
            created_at=datetime.now(),
            theme="Test theme",
            tokens=900,
            short_term_refs=["sum-1"],
        )
        await memory.add_long_term_theme(theme)

        mock_process = MagicMock()
        mock_process.id = "process-1"
        mock_process.state = ProcessState.COMPLETE
        mock_process.properties = {"answer": "Result", "__total_tokens__": 50}

        mock_engine.create_process = AsyncMock(return_value=mock_process)
        mock_engine.start_process = AsyncMock()
        mock_engine.store.load_process = AsyncMock(return_value=mock_process)

        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            memory=memory,
            provider="anthropic",
        )

        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "workflow_name": "Test Workflow",
            "create_new": False,
            "reasoning": "Matches",
        })

        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(return_value=mock_response)
        loop._llm = mock_llm

        # This should attempt long-term compaction but workflow doesn't exist
        result = await loop.process_goal("Test goal")

        assert result.success is True


class TestAddToMemoryOutputTypes:
    """Tests for _add_to_memory with different output types."""

    async def test_add_to_memory_list_output(self, library, mock_engine, metrics, memory):
        """Test adding with list output (falls into else branch)."""
        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            memory=memory,
            provider="anthropic",
        )

        run = WorkflowRun.create("TestWorkflow", "Test goal")
        run.started_at = datetime.now()

        # List triggers the else branch (not str, not dict)
        await loop._add_to_memory(run, ["item1", "item2", "item3"])

        entries = await memory.get_short_term_entries()
        assert len(entries) == 1
        assert "item1" in entries[0].result_summary

    async def test_add_to_memory_number_output(self, library, mock_engine, metrics, memory):
        """Test adding with numeric output."""
        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            memory=memory,
            provider="anthropic",
        )

        run = WorkflowRun.create("TestWorkflow", "Test goal")
        run.started_at = datetime.now()

        await loop._add_to_memory(run, 42)

        entries = await memory.get_short_term_entries()
        assert len(entries) == 1
        assert "42" in entries[0].result_summary

    async def test_add_to_memory_none_output(self, library, mock_engine, metrics, memory):
        """Test adding with None output."""
        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            memory=memory,
            provider="anthropic",
        )

        run = WorkflowRun.create("TestWorkflow", "Test goal")
        run.started_at = datetime.now()

        await loop._add_to_memory(run, None)

        entries = await memory.get_short_term_entries()
        assert len(entries) == 1
        assert "None" in entries[0].result_summary


class TestCompactShortTermMemoryExecution:
    """Tests for short-term memory compaction with full execution."""

    async def test_compact_short_term_successful_execution(
        self, library, mock_engine, metrics, memory
    ):
        """Test successful short-term compaction with workflow execution."""
        # Create the compact workflow
        compact_yaml = """name: "Memory Compact Short"
description: "Compact short-term memory"
tags: ["memory"]
version: 1
first_task: summarize
tasks:
  summarize:
    name: "Summarize"
    action: llm_call
    auto: true
    properties:
      prompt: "{{memory_content}}"
      output_key: short_term_summary
routings: []
"""
        (library.library_path / "compact_short.yaml").write_text(compact_yaml)

        # Add entries to memory
        for i in range(3):
            entry = MemoryEntry(
                id=f"test-{i}",
                timestamp=datetime.now(),
                goal=f"Goal {i}",
                workflow_used="Test",
                result_summary=f"Result {i}",
                tokens=100,
            )
            await memory.add_entry(entry)

        # Setup mock engine
        mock_process = MagicMock()
        mock_process.id = "compact-1"
        mock_process.state = ProcessState.COMPLETE
        mock_process.properties = {"short_term_summary": "Summarized content"}

        mock_engine.create_process = AsyncMock(return_value=mock_process)
        mock_engine.start_process = AsyncMock()
        mock_engine.store.load_process = AsyncMock(return_value=mock_process)

        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            memory=memory,
            provider="anthropic",
        )

        await loop._compact_short_term_memory()

        # Check that entries were cleared
        entries = await memory.get_short_term_entries()
        assert len(entries) == 0

        # Check that summary was added
        summaries = await memory.get_short_term_summaries()
        assert len(summaries) == 1
        assert summaries[0].summary == "Summarized content"
        assert summaries[0].entry_count == 3

    async def test_compact_short_term_workflow_failed(
        self, library, mock_engine, metrics, memory
    ):
        """Test short-term compaction when workflow fails."""
        # Create the compact workflow
        compact_yaml = """name: "Memory Compact Short"
description: "Compact short-term memory"
tags: ["memory"]
version: 1
first_task: summarize
tasks:
  summarize:
    name: "Summarize"
    action: llm_call
    auto: true
    properties:
      prompt: "{{memory_content}}"
      output_key: short_term_summary
routings: []
"""
        (library.library_path / "compact_short.yaml").write_text(compact_yaml)

        # Add entries
        entry = MemoryEntry(
            id="test-1",
            timestamp=datetime.now(),
            goal="Goal",
            workflow_used="Test",
            result_summary="Result",
            tokens=100,
        )
        await memory.add_entry(entry)

        # Setup mock engine to fail
        mock_process = MagicMock()
        mock_process.id = "compact-1"
        mock_process.state = ProcessState.FAILED
        mock_process.error = "Failed"

        mock_engine.create_process = AsyncMock(return_value=mock_process)
        mock_engine.start_process = AsyncMock()
        mock_engine.store.load_process = AsyncMock(return_value=mock_process)

        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            memory=memory,
            provider="anthropic",
        )

        await loop._compact_short_term_memory()

        # Entries should still be there since workflow failed
        entries = await memory.get_short_term_entries()
        assert len(entries) == 1

    async def test_compact_short_term_workflow_timeout(
        self, library, mock_engine, metrics, memory
    ):
        """Test short-term compaction when workflow times out."""
        # Create the compact workflow
        compact_yaml = """name: "Memory Compact Short"
description: "Compact short-term memory"
tags: ["memory"]
version: 1
first_task: summarize
tasks:
  summarize:
    name: "Summarize"
    action: llm_call
    auto: true
    properties:
      prompt: "{{memory_content}}"
      output_key: short_term_summary
routings: []
"""
        (library.library_path / "compact_short.yaml").write_text(compact_yaml)

        # Add entries
        entry = MemoryEntry(
            id="test-1",
            timestamp=datetime.now(),
            goal="Goal",
            workflow_used="Test",
            result_summary="Result",
            tokens=100,
        )
        await memory.add_entry(entry)

        # Setup mock engine to keep running (timeout)
        mock_process = MagicMock()
        mock_process.id = "compact-1"
        mock_process.state = ProcessState.RUNNING

        mock_engine.create_process = AsyncMock(return_value=mock_process)
        mock_engine.start_process = AsyncMock()
        mock_engine.store.load_process = AsyncMock(return_value=mock_process)

        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            memory=memory,
            provider="anthropic",
        )

        import asyncio
        with patch.object(asyncio, "sleep", new_callable=AsyncMock):
            await loop._compact_short_term_memory()

        # Entries should still be there since workflow timed out
        entries = await memory.get_short_term_entries()
        assert len(entries) == 1

    async def test_compact_short_term_no_summary_output(
        self, library, mock_engine, metrics, memory
    ):
        """Test short-term compaction when workflow doesn't output summary."""
        # Create the compact workflow
        compact_yaml = """name: "Memory Compact Short"
description: "Compact short-term memory"
tags: ["memory"]
version: 1
first_task: summarize
tasks:
  summarize:
    name: "Summarize"
    action: llm_call
    auto: true
    properties:
      prompt: "{{memory_content}}"
      output_key: short_term_summary
routings: []
"""
        (library.library_path / "compact_short.yaml").write_text(compact_yaml)

        # Add entries
        entry = MemoryEntry(
            id="test-1",
            timestamp=datetime.now(),
            goal="Goal",
            workflow_used="Test",
            result_summary="Result",
            tokens=100,
        )
        await memory.add_entry(entry)

        # Setup mock engine to complete but without summary
        mock_process = MagicMock()
        mock_process.id = "compact-1"
        mock_process.state = ProcessState.COMPLETE
        mock_process.properties = {}  # No summary

        mock_engine.create_process = AsyncMock(return_value=mock_process)
        mock_engine.start_process = AsyncMock()
        mock_engine.store.load_process = AsyncMock(return_value=mock_process)

        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            memory=memory,
            provider="anthropic",
        )

        await loop._compact_short_term_memory()

        # Entries should still be there since no summary was output
        entries = await memory.get_short_term_entries()
        assert len(entries) == 1


class TestCompactLongTermMemoryExecution:
    """Tests for long-term memory compaction with full execution."""

    async def test_compact_long_term_successful_execution(
        self, library, mock_engine, metrics, memory
    ):
        """Test successful long-term compaction with workflow execution."""
        # Create the compact workflow
        compact_yaml = """name: "Memory Compact Long"
description: "Compact long-term memory"
tags: ["memory"]
version: 1
first_task: extract
tasks:
  extract:
    name: "Extract themes"
    action: llm_call
    auto: true
    properties:
      prompt: "{{memory_content}}"
      output_key: long_term_themes
routings: []
"""
        (library.library_path / "compact_long.yaml").write_text(compact_yaml)

        # Add summaries
        for i in range(3):
            summary = ShortTermSummary(
                id=f"sum-{i}",
                created_at=datetime.now(),
                summary=f"Summary {i}",
                tokens=100,
                entry_count=5,
            )
            await memory.add_short_term_summary(summary)

        # Setup mock engine
        mock_process = MagicMock()
        mock_process.id = "compact-1"
        mock_process.state = ProcessState.COMPLETE
        mock_process.properties = {"long_term_themes": "Extracted themes content"}

        mock_engine.create_process = AsyncMock(return_value=mock_process)
        mock_engine.start_process = AsyncMock()
        mock_engine.store.load_process = AsyncMock(return_value=mock_process)

        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            memory=memory,
            provider="anthropic",
        )

        await loop._compact_long_term_memory()

        # Check that theme was added
        themes = await memory.get_long_term_themes()
        assert len(themes) == 1
        assert themes[0].theme == "Extracted themes content"
        assert len(themes[0].short_term_refs) == 3

    async def test_compact_long_term_workflow_failed(
        self, library, mock_engine, metrics, memory
    ):
        """Test long-term compaction when workflow fails."""
        # Create the compact workflow
        compact_yaml = """name: "Memory Compact Long"
description: "Compact long-term memory"
tags: ["memory"]
version: 1
first_task: extract
tasks:
  extract:
    name: "Extract themes"
    action: llm_call
    auto: true
    properties:
      prompt: "{{memory_content}}"
      output_key: long_term_themes
routings: []
"""
        (library.library_path / "compact_long.yaml").write_text(compact_yaml)

        # Add summary
        summary = ShortTermSummary(
            id="sum-1",
            created_at=datetime.now(),
            summary="Summary",
            tokens=100,
            entry_count=5,
        )
        await memory.add_short_term_summary(summary)

        # Setup mock engine to fail
        mock_process = MagicMock()
        mock_process.id = "compact-1"
        mock_process.state = ProcessState.FAILED
        mock_process.error = "Failed"

        mock_engine.create_process = AsyncMock(return_value=mock_process)
        mock_engine.start_process = AsyncMock()
        mock_engine.store.load_process = AsyncMock(return_value=mock_process)

        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            memory=memory,
            provider="anthropic",
        )

        await loop._compact_long_term_memory()

        # Summaries should still be there since workflow failed
        summaries = await memory.get_short_term_summaries()
        assert len(summaries) == 1

    async def test_compact_long_term_workflow_timeout(
        self, library, mock_engine, metrics, memory
    ):
        """Test long-term compaction when workflow times out."""
        # Create the compact workflow
        compact_yaml = """name: "Memory Compact Long"
description: "Compact long-term memory"
tags: ["memory"]
version: 1
first_task: extract
tasks:
  extract:
    name: "Extract themes"
    action: llm_call
    auto: true
    properties:
      prompt: "{{memory_content}}"
      output_key: long_term_themes
routings: []
"""
        (library.library_path / "compact_long.yaml").write_text(compact_yaml)

        # Add summary
        summary = ShortTermSummary(
            id="sum-1",
            created_at=datetime.now(),
            summary="Summary",
            tokens=100,
            entry_count=5,
        )
        await memory.add_short_term_summary(summary)

        # Setup mock engine to keep running (timeout)
        mock_process = MagicMock()
        mock_process.id = "compact-1"
        mock_process.state = ProcessState.RUNNING

        mock_engine.create_process = AsyncMock(return_value=mock_process)
        mock_engine.start_process = AsyncMock()
        mock_engine.store.load_process = AsyncMock(return_value=mock_process)

        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            memory=memory,
            provider="anthropic",
        )

        import asyncio
        with patch.object(asyncio, "sleep", new_callable=AsyncMock):
            await loop._compact_long_term_memory()

        # Summaries should still be there since workflow timed out
        summaries = await memory.get_short_term_summaries()
        assert len(summaries) == 1

    async def test_compact_long_term_no_theme_output(
        self, library, mock_engine, metrics, memory
    ):
        """Test long-term compaction when workflow doesn't output themes."""
        # Create the compact workflow
        compact_yaml = """name: "Memory Compact Long"
description: "Compact long-term memory"
tags: ["memory"]
version: 1
first_task: extract
tasks:
  extract:
    name: "Extract themes"
    action: llm_call
    auto: true
    properties:
      prompt: "{{memory_content}}"
      output_key: long_term_themes
routings: []
"""
        (library.library_path / "compact_long.yaml").write_text(compact_yaml)

        # Add summary
        summary = ShortTermSummary(
            id="sum-1",
            created_at=datetime.now(),
            summary="Summary",
            tokens=100,
            entry_count=5,
        )
        await memory.add_short_term_summary(summary)

        # Setup mock engine to complete but without themes
        mock_process = MagicMock()
        mock_process.id = "compact-1"
        mock_process.state = ProcessState.COMPLETE
        mock_process.properties = {}  # No themes

        mock_engine.create_process = AsyncMock(return_value=mock_process)
        mock_engine.start_process = AsyncMock()
        mock_engine.store.load_process = AsyncMock(return_value=mock_process)

        loop = AgentLoop(
            library=library,
            engine=mock_engine,
            metrics=metrics,
            memory=memory,
            provider="anthropic",
        )

        await loop._compact_long_term_memory()

        # Summaries should still be there since no themes output
        summaries = await memory.get_short_term_summaries()
        assert len(summaries) == 1
