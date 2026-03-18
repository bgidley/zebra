"""Tests for QueueGoalAction."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from zebra_tasks.agent.queue_goal import QueueGoalAction


@pytest.fixture
def mock_task():
    """Create a mock task instance."""
    task = MagicMock()
    task.id = "task-1"
    task.properties = {}
    return task


@pytest.fixture
def mock_library():
    """Create a mock workflow library."""
    lib = MagicMock()
    lib.get_workflow = MagicMock(return_value=MagicMock(name="Agent Main Loop"))
    lib.list_workflows = AsyncMock(return_value=[])
    return lib


@pytest.fixture
def mock_context(mock_library):
    """Create a mock execution context."""
    context = MagicMock()
    context.process = MagicMock()
    context.process.id = "parent-process-1"
    context.process.properties = {}
    context.extras = {
        "__workflow_library__": mock_library,
    }
    context.get_process_property = MagicMock(
        side_effect=lambda k, d=None: context.process.properties.get(k, d)
    )
    context.set_process_property = MagicMock(
        side_effect=lambda k, v: context.process.properties.__setitem__(k, v)
    )
    context.resolve_template = MagicMock(side_effect=lambda x: x)

    # Mock engine with create_process
    mock_process = MagicMock()
    mock_process.id = "queued-process-123"
    context.engine = MagicMock()
    context.engine.create_process = AsyncMock(return_value=mock_process)

    return context


class TestQueueGoalAction:
    """Tests for QueueGoalAction."""

    async def test_queues_goal_successfully(self, mock_task, mock_context):
        """Successfully queues a goal as a CREATED process."""
        mock_task.properties = {"goal": "Write a poem", "priority": "4"}
        action = QueueGoalAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.output["queued"] is True
        assert result.output["process_id"] == "queued-process-123"
        assert result.output["priority"] == 4

    async def test_no_goal_fails(self, mock_task, mock_context):
        """Fails when no goal is provided."""
        mock_task.properties = {"goal": ""}
        action = QueueGoalAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is False

    async def test_default_priority(self, mock_task, mock_context):
        """Default priority is 3."""
        mock_task.properties = {"goal": "Test goal"}
        action = QueueGoalAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.output["priority"] == 3

    async def test_priority_clamped(self, mock_task, mock_context):
        """Priority is clamped to 1-5 range."""
        mock_task.properties = {"goal": "Test goal", "priority": "99"}
        action = QueueGoalAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.output["priority"] == 5

    async def test_priority_clamped_low(self, mock_task, mock_context):
        """Priority is clamped to minimum 1."""
        mock_task.properties = {"goal": "Test goal", "priority": "-5"}
        action = QueueGoalAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.output["priority"] == 1

    async def test_invalid_priority_defaults(self, mock_task, mock_context):
        """Invalid priority string defaults to 3."""
        mock_task.properties = {"goal": "Test goal", "priority": "invalid"}
        action = QueueGoalAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.output["priority"] == 3

    async def test_with_deadline(self, mock_task, mock_context):
        """Deadline is passed through to the result."""
        mock_task.properties = {
            "goal": "Test goal",
            "deadline": "2026-03-14T18:00:00Z",
        }
        action = QueueGoalAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        assert result.output["deadline"] == "2026-03-14T18:00:00Z"

    async def test_no_library_fails(self, mock_task, mock_context):
        """Fails when no workflow library is available."""
        mock_context.extras = {}
        mock_task.properties = {"goal": "Test goal"}
        action = QueueGoalAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is False
        assert "library" in result.output.lower() if isinstance(result.output, str) else True

    async def test_copies_llm_settings(self, mock_task, mock_context):
        """Copies LLM settings from parent process."""
        mock_context.process.properties = {
            "__llm_provider_name__": "anthropic",
            "__llm_model__": "claude-haiku-4-20250414",
        }
        mock_task.properties = {"goal": "Test goal"}
        action = QueueGoalAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        # Check that create_process was called with properties that include LLM settings
        call_args = mock_context.engine.create_process.call_args
        created_props = call_args[1].get(
            "properties", call_args[0][1] if len(call_args[0]) > 1 else {}
        )
        assert created_props.get("__llm_provider_name__") == "anthropic"
        assert created_props.get("__llm_model__") == "claude-haiku-4-20250414"

    async def test_sets_output_key(self, mock_task, mock_context):
        """Result is stored under the specified output key."""
        mock_task.properties = {"goal": "Test goal", "output_key": "my_result"}
        action = QueueGoalAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is True
        mock_context.set_process_property.assert_called_with("my_result", result.output)

    async def test_create_process_failure(self, mock_task, mock_context):
        """Handles create_process failure gracefully."""
        mock_context.engine.create_process = AsyncMock(side_effect=Exception("DB error"))
        mock_task.properties = {"goal": "Test goal"}
        action = QueueGoalAction()
        result = await action.run(mock_task, mock_context)

        assert result.success is False
        # Error is stored in result.error (TaskResult.fail sets error, not output)
        assert "DB error" in str(result.error)


class TestQueueGoalActionMetadata:
    """Tests for QueueGoalAction metadata."""

    def test_has_description(self):
        action = QueueGoalAction()
        assert action.description

    def test_has_inputs(self):
        action = QueueGoalAction()
        assert len(action.inputs) > 0
        input_names = [i.name for i in action.inputs]
        assert "goal" in input_names
        assert "priority" in input_names
        assert "deadline" in input_names

    def test_has_outputs(self):
        action = QueueGoalAction()
        assert len(action.outputs) > 0
        output_names = [o.name for o in action.outputs]
        assert "queued" in output_names
        assert "process_id" in output_names
