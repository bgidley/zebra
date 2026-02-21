"""Tests for agent loop task actions.

These actions were created to support the workflow-based agent loop:
- MemoryCheckAction - Check if memory needs compaction
- RecordMetricsAction - Record workflow run to metrics store
- UpdateMemoryAction - Add memory entry for completed run
- ExecuteGoalWorkflowAction - Execute a goal workflow by name
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_task():
    """Create a mock task instance."""
    task = MagicMock()
    task.id = "task-1"
    task.properties = {}
    return task


@pytest.fixture
def mock_context():
    """Create a mock execution context."""
    context = MagicMock()
    context.process = MagicMock()
    context.process.id = "process-1"
    context.process.properties = {}
    context.extras = {}  # For engine-level dependency injection (non-serializable objects)
    context.get_process_property = MagicMock(
        side_effect=lambda k, d=None: context.process.properties.get(k, d)
    )
    context.set_process_property = MagicMock(
        side_effect=lambda k, v: context.process.properties.__setitem__(k, v)
    )
    context.resolve_template = MagicMock(side_effect=lambda x: x)
    return context


@pytest.fixture
def mock_memory_store():
    """Create a mock memory store."""
    store = MagicMock()
    store.needs_short_term_compaction = AsyncMock(return_value=False)
    store.needs_long_term_compaction = AsyncMock(return_value=False)
    store.add_entry = AsyncMock()
    return store


@pytest.fixture
def mock_metrics_store():
    """Create a mock metrics store."""
    store = MagicMock()
    store.record_run = AsyncMock()
    store.record_task_executions = AsyncMock()
    return store


# =============================================================================
# MemoryCheckAction Tests
# =============================================================================


class TestMemoryCheckAction:
    """Tests for MemoryCheckAction."""

    async def test_no_memory_store_returns_continue(self, mock_task, mock_context):
        """Test that no memory store returns 'continue' route."""
        from zebra_tasks.agent.memory_check import MemoryCheckAction

        action = MemoryCheckAction()

        result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.next_route == "continue"
        assert result.output["needs_short_term"] is False
        assert result.output["needs_long_term"] is False

    async def test_no_compaction_needed(self, mock_task, mock_context, mock_memory_store):
        """Test when no compaction is needed."""
        from zebra_tasks.agent.memory_check import MemoryCheckAction

        mock_memory_store.needs_short_term_compaction.return_value = False
        mock_memory_store.needs_long_term_compaction.return_value = False
        mock_context.extras["__memory_store__"] = mock_memory_store

        action = MemoryCheckAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.next_route == "continue"
        assert result.output["needs_short_term"] is False
        assert result.output["needs_long_term"] is False

    async def test_short_term_compaction_needed(self, mock_task, mock_context, mock_memory_store):
        """Test when short-term compaction is needed."""
        from zebra_tasks.agent.memory_check import MemoryCheckAction

        mock_memory_store.needs_short_term_compaction.return_value = True
        mock_memory_store.needs_long_term_compaction.return_value = False
        mock_context.extras["__memory_store__"] = mock_memory_store

        action = MemoryCheckAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.next_route == "compact_short"
        assert result.output["needs_short_term"] is True
        assert result.output["needs_long_term"] is False

    async def test_long_term_compaction_needed(self, mock_task, mock_context, mock_memory_store):
        """Test when only long-term compaction is needed."""
        from zebra_tasks.agent.memory_check import MemoryCheckAction

        mock_memory_store.needs_short_term_compaction.return_value = False
        mock_memory_store.needs_long_term_compaction.return_value = True
        mock_context.extras["__memory_store__"] = mock_memory_store

        action = MemoryCheckAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.next_route == "compact_long"
        assert result.output["needs_short_term"] is False
        assert result.output["needs_long_term"] is True

    async def test_both_compaction_needed_prioritizes_short(
        self, mock_task, mock_context, mock_memory_store
    ):
        """Test when both compactions are needed, short-term is prioritized."""
        from zebra_tasks.agent.memory_check import MemoryCheckAction

        mock_memory_store.needs_short_term_compaction.return_value = True
        mock_memory_store.needs_long_term_compaction.return_value = True
        mock_context.extras["__memory_store__"] = mock_memory_store

        action = MemoryCheckAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.next_route == "compact_short"
        assert result.output["needs_short_term"] is True
        assert result.output["needs_long_term"] is True

    async def test_custom_output_key(self, mock_task, mock_context, mock_memory_store):
        """Test using a custom output key."""
        from zebra_tasks.agent.memory_check import MemoryCheckAction

        mock_memory_store.needs_short_term_compaction.return_value = False
        mock_memory_store.needs_long_term_compaction.return_value = False
        mock_context.extras["__memory_store__"] = mock_memory_store
        mock_task.properties["output_key"] = "custom_status"

        action = MemoryCheckAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        # Verify the custom key was set
        mock_context.set_process_property.assert_called()
        call_args = mock_context.set_process_property.call_args
        assert call_args[0][0] == "custom_status"

    async def test_injected_memory_store(self, mock_task, mock_context, mock_memory_store):
        """Test using an injected memory store."""
        from zebra_tasks.agent.memory_check import MemoryCheckAction

        mock_memory_store.needs_short_term_compaction.return_value = True
        mock_memory_store.needs_long_term_compaction.return_value = False

        # Inject via constructor
        action = MemoryCheckAction(memory_store=mock_memory_store)
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.next_route == "compact_short"

    async def test_memory_check_error_handling(self, mock_task, mock_context, mock_memory_store):
        """Test error handling when memory check fails."""
        from zebra_tasks.agent.memory_check import MemoryCheckAction

        mock_memory_store.needs_short_term_compaction.side_effect = Exception("Store error")
        mock_context.extras["__memory_store__"] = mock_memory_store

        action = MemoryCheckAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is False
        assert "Memory check failed" in result.error


# =============================================================================
# RecordMetricsAction Tests
# =============================================================================


class TestRecordMetricsAction:
    """Tests for RecordMetricsAction."""

    async def test_no_metrics_store_succeeds_silently(self, mock_task, mock_context):
        """Test that no metrics store still succeeds but marks as not recorded."""
        from zebra_tasks.agent.record_metrics import RecordMetricsAction

        mock_task.properties = {
            "run_id": "run-1",
            "workflow_name": "Test Workflow",
            "goal": "Test goal",
            "success": True,
        }

        action = RecordMetricsAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.output["recorded"] is False

    async def test_record_successful_run(self, mock_task, mock_context, mock_metrics_store):
        """Test recording a successful workflow run."""
        from zebra_tasks.agent.record_metrics import RecordMetricsAction

        mock_context.extras["__metrics_store__"] = mock_metrics_store
        mock_task.properties = {
            "run_id": "run-1",
            "workflow_name": "Test Workflow",
            "goal": "Test goal",
            "success": True,
            "output": {"result": "success"},
            "tokens_used": 100,
        }

        action = RecordMetricsAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.output["recorded"] is True
        mock_metrics_store.record_run.assert_called_once()

        # Verify the recorded run
        recorded_run = mock_metrics_store.record_run.call_args[0][0]
        assert recorded_run.id == "run-1"
        assert recorded_run.workflow_name == "Test Workflow"
        assert recorded_run.goal == "Test goal"
        assert recorded_run.success is True
        assert recorded_run.tokens_used == 100

    async def test_record_failed_run(self, mock_task, mock_context, mock_metrics_store):
        """Test recording a failed workflow run."""
        from zebra_tasks.agent.record_metrics import RecordMetricsAction

        mock_context.extras["__metrics_store__"] = mock_metrics_store
        mock_task.properties = {
            "run_id": "run-1",
            "workflow_name": "Test Workflow",
            "goal": "Test goal",
            "success": False,
            "error": "Something went wrong",
        }

        action = RecordMetricsAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.output["recorded"] is True

        recorded_run = mock_metrics_store.record_run.call_args[0][0]
        assert recorded_run.success is False
        assert recorded_run.error == "Something went wrong"

    async def test_record_with_task_executions(self, mock_task, mock_context, mock_metrics_store):
        """Test recording run with task executions."""
        from zebra_tasks.agent.record_metrics import RecordMetricsAction

        mock_context.extras["__metrics_store__"] = mock_metrics_store
        mock_context.process.properties["__task_executions__"] = [
            {"id": "exec-1", "task_name": "Task 1"},
            {"id": "exec-2", "task_name": "Task 2"},
        ]
        mock_task.properties = {
            "run_id": "run-1",
            "workflow_name": "Test Workflow",
            "goal": "Test goal",
            "success": True,
        }

        action = RecordMetricsAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        mock_metrics_store.record_task_executions.assert_called_once()

    async def test_record_with_started_at(self, mock_task, mock_context, mock_metrics_store):
        """Test recording run with explicit started_at timestamp."""
        from zebra_tasks.agent.record_metrics import RecordMetricsAction

        mock_context.extras["__metrics_store__"] = mock_metrics_store
        started_at = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        mock_task.properties = {
            "run_id": "run-1",
            "workflow_name": "Test Workflow",
            "goal": "Test goal",
            "success": True,
            "started_at": started_at.isoformat(),
        }

        action = RecordMetricsAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        recorded_run = mock_metrics_store.record_run.call_args[0][0]
        assert recorded_run.started_at == started_at

    async def test_injected_metrics_store(self, mock_task, mock_context, mock_metrics_store):
        """Test using an injected metrics store."""
        from zebra_tasks.agent.record_metrics import RecordMetricsAction

        mock_task.properties = {
            "run_id": "run-1",
            "workflow_name": "Test Workflow",
            "goal": "Test goal",
            "success": True,
        }

        action = RecordMetricsAction(metrics_store=mock_metrics_store)
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.output["recorded"] is True
        mock_metrics_store.record_run.assert_called_once()

    async def test_record_error_handling(self, mock_task, mock_context, mock_metrics_store):
        """Test error handling when recording fails."""
        from zebra_tasks.agent.record_metrics import RecordMetricsAction

        mock_metrics_store.record_run.side_effect = Exception("Database error")
        mock_context.extras["__metrics_store__"] = mock_metrics_store
        mock_task.properties = {
            "run_id": "run-1",
            "workflow_name": "Test Workflow",
            "goal": "Test goal",
            "success": True,
        }

        action = RecordMetricsAction()
        result = await action.run(mock_task, mock_context)

        # Should succeed but mark as not recorded
        assert result.success is True
        assert result.output["recorded"] is False
        assert "Database error" in result.output.get("error", "")

    async def test_serialize_complex_output(self, mock_task, mock_context, mock_metrics_store):
        """Test serialization of complex output types."""
        from zebra_tasks.agent.record_metrics import RecordMetricsAction

        mock_context.extras["__metrics_store__"] = mock_metrics_store
        mock_task.properties = {
            "run_id": "run-1",
            "workflow_name": "Test Workflow",
            "goal": "Test goal",
            "success": True,
            "output": {"nested": {"value": [1, 2, 3]}, "string": "test"},
        }

        action = RecordMetricsAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        recorded_run = mock_metrics_store.record_run.call_args[0][0]
        assert recorded_run.output == {"nested": {"value": [1, 2, 3]}, "string": "test"}


# =============================================================================
# UpdateMemoryAction Tests
# =============================================================================


class TestUpdateMemoryAction:
    """Tests for UpdateMemoryAction."""

    async def test_no_memory_store_succeeds_silently(self, mock_task, mock_context):
        """Test that no memory store still succeeds but marks as not added."""
        from zebra_tasks.agent.update_memory import UpdateMemoryAction

        mock_task.properties = {
            "run_id": "run-1",
            "goal": "Test goal",
            "workflow_name": "Test Workflow",
            "result_summary": "Test result",
        }

        action = UpdateMemoryAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.output["added"] is False

    async def test_add_memory_entry(self, mock_task, mock_context, mock_memory_store):
        """Test adding a memory entry."""
        from zebra_tasks.agent.update_memory import UpdateMemoryAction

        mock_context.extras["__memory_store__"] = mock_memory_store
        mock_task.properties = {
            "run_id": "run-1",
            "goal": "Test goal",
            "workflow_name": "Test Workflow",
            "result_summary": "Test result",
        }

        action = UpdateMemoryAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.output["added"] is True
        mock_memory_store.add_entry.assert_called_once()

        # Verify the entry
        entry = mock_memory_store.add_entry.call_args[0][0]
        assert entry.goal == "Test goal"
        assert entry.workflow_used == "Test Workflow"
        assert entry.result_summary == "Test result"

    async def test_add_memory_with_dict_result(self, mock_task, mock_context, mock_memory_store):
        """Test adding memory with dict result_summary."""
        from zebra_tasks.agent.update_memory import UpdateMemoryAction

        mock_context.extras["__memory_store__"] = mock_memory_store
        mock_task.properties = {
            "run_id": "run-1",
            "goal": "Test goal",
            "workflow_name": "Test Workflow",
            "result_summary": {"response": "This is the response"},
        }

        action = UpdateMemoryAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        entry = mock_memory_store.add_entry.call_args[0][0]
        assert entry.result_summary == "This is the response"

    async def test_add_memory_with_output_key_result(
        self, mock_task, mock_context, mock_memory_store
    ):
        """Test adding memory with 'output' key in result."""
        from zebra_tasks.agent.update_memory import UpdateMemoryAction

        mock_context.extras["__memory_store__"] = mock_memory_store
        mock_task.properties = {
            "run_id": "run-1",
            "goal": "Test goal",
            "workflow_name": "Test Workflow",
            "result_summary": {"output": "Output value"},
        }

        action = UpdateMemoryAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        entry = mock_memory_store.add_entry.call_args[0][0]
        assert entry.result_summary == "Output value"

    async def test_truncate_long_summary(self, mock_task, mock_context, mock_memory_store):
        """Test that long summaries are truncated."""
        from zebra_tasks.agent.update_memory import UpdateMemoryAction

        mock_context.extras["__memory_store__"] = mock_memory_store
        long_text = "x" * 1000
        mock_task.properties = {
            "run_id": "run-1",
            "goal": "Test goal",
            "workflow_name": "Test Workflow",
            "result_summary": long_text,
        }

        action = UpdateMemoryAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        entry = mock_memory_store.add_entry.call_args[0][0]
        assert len(entry.result_summary) <= 500
        assert entry.result_summary.endswith("...")

    async def test_injected_memory_store(self, mock_task, mock_context, mock_memory_store):
        """Test using an injected memory store."""
        from zebra_tasks.agent.update_memory import UpdateMemoryAction

        mock_task.properties = {
            "run_id": "run-1",
            "goal": "Test goal",
            "workflow_name": "Test Workflow",
            "result_summary": "Test result",
        }

        action = UpdateMemoryAction(memory_store=mock_memory_store)
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.output["added"] is True

    async def test_update_error_handling(self, mock_task, mock_context, mock_memory_store):
        """Test error handling when update fails."""
        from zebra_tasks.agent.update_memory import UpdateMemoryAction

        mock_memory_store.add_entry.side_effect = Exception("Memory error")
        mock_context.extras["__memory_store__"] = mock_memory_store
        mock_task.properties = {
            "run_id": "run-1",
            "goal": "Test goal",
            "workflow_name": "Test Workflow",
            "result_summary": "Test result",
        }

        action = UpdateMemoryAction()
        result = await action.run(mock_task, mock_context)

        # Should succeed but mark as not added
        assert result.success is True
        assert result.output["added"] is False
        assert "Memory error" in result.output.get("error", "")

    async def test_none_result_summary(self, mock_task, mock_context, mock_memory_store):
        """Test handling None result_summary."""
        from zebra_tasks.agent.update_memory import UpdateMemoryAction

        mock_context.extras["__memory_store__"] = mock_memory_store
        mock_task.properties = {
            "run_id": "run-1",
            "goal": "Test goal",
            "workflow_name": "Test Workflow",
            "result_summary": None,
        }

        action = UpdateMemoryAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        entry = mock_memory_store.add_entry.call_args[0][0]
        assert entry.result_summary == ""


# =============================================================================
# ExecuteGoalWorkflowAction Tests
# =============================================================================


class TestExecuteGoalWorkflowAction:
    """Tests for ExecuteGoalWorkflowAction."""

    @pytest.fixture
    def mock_workflow_library(self):
        """Create a mock workflow library."""
        library = MagicMock()
        library.get_workflow = MagicMock()
        return library

    @pytest.fixture
    def mock_definition(self):
        """Create a mock process definition."""
        definition = MagicMock()
        definition.tasks = {"task1": MagicMock(name="Task 1")}
        return definition

    @pytest.fixture
    def mock_engine(self):
        """Create a mock workflow engine."""
        engine = MagicMock()
        engine.create_process = AsyncMock()
        engine.start_process = AsyncMock()
        return engine

    @pytest.fixture
    def mock_store(self):
        """Create a mock state store."""
        store = MagicMock()
        store.load_process = AsyncMock()
        store.save_process = AsyncMock()
        return store

    async def test_no_workflow_name(self, mock_task, mock_context):
        """Test error when no workflow_name provided."""
        from zebra_tasks.agent.execute_workflow import ExecuteGoalWorkflowAction

        mock_task.properties = {"goal": "Test goal"}

        action = ExecuteGoalWorkflowAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is False
        assert "No workflow_name provided" in result.error

    async def test_no_goal(self, mock_task, mock_context):
        """Test error when no goal provided."""
        from zebra_tasks.agent.execute_workflow import ExecuteGoalWorkflowAction

        mock_task.properties = {"workflow_name": "Test Workflow"}

        action = ExecuteGoalWorkflowAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is False
        assert "No goal provided" in result.error

    async def test_no_workflow_library(self, mock_task, mock_context):
        """Test error when no workflow library available."""
        from zebra_tasks.agent.execute_workflow import ExecuteGoalWorkflowAction

        mock_task.properties = {
            "workflow_name": "Test Workflow",
            "goal": "Test goal",
        }

        action = ExecuteGoalWorkflowAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is False
        assert "No workflow library available" in result.error

    async def test_workflow_not_found(self, mock_task, mock_context, mock_workflow_library):
        """Test error when workflow not found."""
        from zebra_tasks.agent.execute_workflow import ExecuteGoalWorkflowAction

        mock_workflow_library.get_workflow.side_effect = ValueError("Workflow not found: Unknown")
        mock_context.extras["__workflow_library__"] = mock_workflow_library
        mock_task.properties = {
            "workflow_name": "Unknown",
            "goal": "Test goal",
        }

        action = ExecuteGoalWorkflowAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is False
        assert "Failed to load workflow" in result.error

    async def test_successful_execution(
        self,
        mock_task,
        mock_context,
        mock_workflow_library,
        mock_definition,
        mock_engine,
        mock_store,
    ):
        """Test successful workflow execution."""
        from zebra.core.models import ProcessState

        from zebra_tasks.agent.execute_workflow import ExecuteGoalWorkflowAction

        # Setup mocks
        mock_workflow_library.get_workflow.return_value = mock_definition
        mock_context.extras["__workflow_library__"] = mock_workflow_library
        mock_context.engine = mock_engine
        mock_context.store = mock_store

        # Create mock sub-process
        mock_sub_process = MagicMock()
        mock_sub_process.id = "sub-process-1"
        mock_sub_process.state = ProcessState.COMPLETE
        mock_sub_process.properties = {"answer": "The answer is 42", "__total_tokens__": 50}
        mock_engine.create_process.return_value = mock_sub_process
        mock_store.load_process.return_value = mock_sub_process

        mock_task.properties = {
            "workflow_name": "Test Workflow",
            "goal": "What is the answer?",
            "timeout": 5,
        }

        action = ExecuteGoalWorkflowAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.output["success"] is True
        assert result.output["output"] == "The answer is 42"
        assert result.output["tokens_used"] == 50

    async def test_failed_execution(
        self,
        mock_task,
        mock_context,
        mock_workflow_library,
        mock_definition,
        mock_engine,
        mock_store,
    ):
        """Test failed workflow execution."""
        from zebra.core.models import ProcessState

        from zebra_tasks.agent.execute_workflow import ExecuteGoalWorkflowAction

        # Setup mocks
        mock_workflow_library.get_workflow.return_value = mock_definition
        mock_context.extras["__workflow_library__"] = mock_workflow_library
        mock_context.engine = mock_engine
        mock_context.store = mock_store

        # Create mock sub-process that fails
        mock_sub_process = MagicMock()
        mock_sub_process.id = "sub-process-1"
        mock_sub_process.state = ProcessState.FAILED
        mock_sub_process.properties = {"__error__": "Task failed", "__total_tokens__": 25}
        mock_engine.create_process.return_value = mock_sub_process
        mock_store.load_process.return_value = mock_sub_process

        mock_task.properties = {
            "workflow_name": "Test Workflow",
            "goal": "What is the answer?",
            "timeout": 5,
        }

        action = ExecuteGoalWorkflowAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is False
        assert "Task failed" in result.error

    async def test_custom_output_key(
        self,
        mock_task,
        mock_context,
        mock_workflow_library,
        mock_definition,
        mock_engine,
        mock_store,
    ):
        """Test using a custom output key."""
        from zebra.core.models import ProcessState

        from zebra_tasks.agent.execute_workflow import ExecuteGoalWorkflowAction

        # Setup mocks
        mock_workflow_library.get_workflow.return_value = mock_definition
        mock_context.extras["__workflow_library__"] = mock_workflow_library
        mock_context.engine = mock_engine
        mock_context.store = mock_store

        mock_sub_process = MagicMock()
        mock_sub_process.id = "sub-process-1"
        mock_sub_process.state = ProcessState.COMPLETE
        mock_sub_process.properties = {"result": "done"}
        mock_engine.create_process.return_value = mock_sub_process
        mock_store.load_process.return_value = mock_sub_process

        mock_task.properties = {
            "workflow_name": "Test Workflow",
            "goal": "Test goal",
            "timeout": 5,
            "output_key": "custom_result",
        }

        action = ExecuteGoalWorkflowAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        # Verify custom key was set
        mock_context.set_process_property.assert_called()
        call_args = mock_context.set_process_property.call_args
        assert call_args[0][0] == "custom_result"

    async def test_inherits_llm_settings(
        self,
        mock_task,
        mock_context,
        mock_workflow_library,
        mock_definition,
        mock_engine,
        mock_store,
    ):
        """Test that LLM settings are inherited from parent process."""
        from zebra.core.models import ProcessState

        from zebra_tasks.agent.execute_workflow import ExecuteGoalWorkflowAction

        # Setup mocks with LLM settings
        mock_workflow_library.get_workflow.return_value = mock_definition
        mock_context.extras["__workflow_library__"] = mock_workflow_library
        mock_context.process.properties["__llm_provider_name__"] = "anthropic"
        mock_context.process.properties["__llm_model__"] = "claude-3-opus"
        mock_context.engine = mock_engine
        mock_context.store = mock_store

        mock_sub_process = MagicMock()
        mock_sub_process.id = "sub-process-1"
        mock_sub_process.state = ProcessState.COMPLETE
        mock_sub_process.properties = {"result": "done"}
        mock_engine.create_process.return_value = mock_sub_process
        mock_store.load_process.return_value = mock_sub_process

        mock_task.properties = {
            "workflow_name": "Test Workflow",
            "goal": "Test goal",
            "timeout": 5,
        }

        action = ExecuteGoalWorkflowAction()
        await action.run(mock_task, mock_context)

        # Check that create_process was called with LLM settings
        create_call = mock_engine.create_process.call_args
        props = create_call[1]["properties"]
        assert props["__llm_provider_name__"] == "anthropic"
        assert props["__llm_model__"] == "claude-3-opus"

    async def test_injected_workflow_library(
        self,
        mock_task,
        mock_context,
        mock_workflow_library,
        mock_definition,
        mock_engine,
        mock_store,
    ):
        """Test using an injected workflow library."""
        from zebra.core.models import ProcessState

        from zebra_tasks.agent.execute_workflow import ExecuteGoalWorkflowAction

        # Setup mocks
        mock_workflow_library.get_workflow.return_value = mock_definition
        mock_context.engine = mock_engine
        mock_context.store = mock_store

        mock_sub_process = MagicMock()
        mock_sub_process.id = "sub-process-1"
        mock_sub_process.state = ProcessState.COMPLETE
        mock_sub_process.properties = {"result": "done"}
        mock_engine.create_process.return_value = mock_sub_process
        mock_store.load_process.return_value = mock_sub_process

        mock_task.properties = {
            "workflow_name": "Test Workflow",
            "goal": "Test goal",
            "timeout": 5,
        }

        # Inject via constructor
        action = ExecuteGoalWorkflowAction(workflow_library=mock_workflow_library)
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        mock_workflow_library.get_workflow.assert_called_once_with("Test Workflow")

    async def test_extract_output_keys(self):
        """Test output extraction from process properties."""
        from zebra_tasks.agent.execute_workflow import ExecuteGoalWorkflowAction

        action = ExecuteGoalWorkflowAction()

        # Test standard keys
        assert action._extract_output({"answer": "test"}) == "test"
        assert action._extract_output({"summary": "test"}) == "test"
        assert action._extract_output({"result": "test"}) == "test"
        assert action._extract_output({"output": "test"}) == "test"

        # Test fallback to non-internal properties
        result = action._extract_output(
            {"custom": "value", "__internal__": "hidden", "other": "data"}
        )
        assert result == {"custom": "value", "other": "data"}
