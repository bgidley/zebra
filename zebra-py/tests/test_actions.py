"""Tests for task actions (shell, prompt, decision)."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from zebra.core.models import (
    TaskInstance,
    TaskState,
    TaskDefinition,
    TaskResult,
    ProcessInstance,
    ProcessState,
)
from zebra.tasks.actions.shell import ShellTaskAction
from zebra.tasks.actions.prompt import PromptTaskAction, DecisionTaskAction
from zebra.tasks.base import ExecutionContext


@pytest.fixture
def mock_context():
    """Create a mock execution context."""
    context = MagicMock(spec=ExecutionContext)
    context.process = ProcessInstance(
        id="proc-1",
        definition_id="def-1",
        state=ProcessState.RUNNING,
        properties={"var": "value"},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    context.task_definition = TaskDefinition(
        id="task-1",
        name="Test Task",
        properties={},
    )
    context.resolve_template = lambda x: x.replace("{{var}}", "value") if isinstance(x, str) else x
    return context


@pytest.fixture
def sample_task():
    """Create a sample task instance."""
    return TaskInstance(
        id="task-inst-1",
        process_id="proc-1",
        task_definition_id="task-1",
        state=TaskState.RUNNING,
        foe_id="foe-1",
        properties={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class TestShellTaskAction:
    """Tests for ShellTaskAction."""

    async def test_simple_command(self, mock_context, sample_task):
        """Test executing a simple command."""
        sample_task.properties["command"] = "echo hello"
        action = ShellTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is True
        assert "hello" in result.output["stdout"]
        assert result.output["returncode"] == 0

    async def test_command_from_definition(self, mock_context, sample_task):
        """Test getting command from task definition."""
        mock_context.task_definition.properties["command"] = "echo from_def"
        action = ShellTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is True
        assert "from_def" in result.output["stdout"]

    async def test_no_command_fails(self, mock_context, sample_task):
        """Test that missing command fails."""
        action = ShellTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is False
        assert "No 'command' property" in result.error

    async def test_template_resolution(self, mock_context, sample_task):
        """Test template variables are resolved in command."""
        sample_task.properties["command"] = "echo {{var}}"
        action = ShellTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is True
        assert "value" in result.output["stdout"]

    async def test_command_failure(self, mock_context, sample_task):
        """Test handling of failed command."""
        sample_task.properties["command"] = "exit 1"
        action = ShellTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is False
        assert result.output["returncode"] == 1
        assert "exited with code 1" in result.error

    async def test_command_with_stderr(self, mock_context, sample_task):
        """Test capturing stderr."""
        sample_task.properties["command"] = "echo error >&2"
        action = ShellTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is True
        assert "error" in result.output["stderr"]

    async def test_command_timeout(self, mock_context, sample_task):
        """Test command timeout."""
        sample_task.properties["command"] = "sleep 10"
        sample_task.properties["timeout"] = 0.1
        action = ShellTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is False
        assert "timed out" in result.error

    async def test_command_with_cwd(self, mock_context, sample_task):
        """Test command with working directory."""
        sample_task.properties["command"] = "pwd"
        sample_task.properties["cwd"] = "/tmp"
        action = ShellTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is True
        assert "/tmp" in result.output["stdout"]

    async def test_command_without_shell(self, mock_context, sample_task):
        """Test command execution without shell."""
        sample_task.properties["command"] = "echo hello"
        sample_task.properties["shell"] = False
        action = ShellTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is True
        assert "hello" in result.output["stdout"]

    async def test_invalid_command(self, mock_context, sample_task):
        """Test handling of invalid command."""
        sample_task.properties["command"] = "nonexistent_command_12345"
        action = ShellTaskAction()

        result = await action.run(sample_task, mock_context)

        # Command not found returns non-zero exit code
        assert result.success is False


class TestPromptTaskAction:
    """Tests for PromptTaskAction."""

    async def test_prompt_with_input(self, mock_context, sample_task):
        """Test prompt with pre-provided input."""
        sample_task.properties["input"] = "user response"
        mock_context.task_definition.properties["prompt"] = "What is your name?"
        action = PromptTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is True
        assert result.output["response"] == "user response"
        assert result.output["prompt"] == "What is your name?"

    async def test_prompt_with_default(self, mock_context, sample_task):
        """Test prompt with default value."""
        mock_context.task_definition.properties["prompt"] = "Enter value:"
        mock_context.task_definition.properties["default"] = "default_value"
        action = PromptTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is True
        assert result.output["response"] == "default_value"

    async def test_prompt_awaiting_input(self, mock_context, sample_task):
        """Test prompt without input or default awaits input."""
        mock_context.task_definition.properties["prompt"] = "Enter value:"
        action = PromptTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is True
        assert result.output["awaiting_input"] is True
        assert sample_task.properties["__prompt__"] == "Enter value:"

    async def test_prompt_with_existing_result(self, mock_context, sample_task):
        """Test prompt returns existing result if present."""
        sample_task.result = {"previous": "result"}
        action = PromptTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is True
        assert result.output == {"previous": "result"}

    async def test_prompt_template_resolution(self, mock_context, sample_task):
        """Test template resolution in prompt."""
        mock_context.task_definition.properties["prompt"] = "Value is {{var}}"
        sample_task.properties["input"] = "ok"
        action = PromptTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.output["prompt"] == "Value is value"

    async def test_prompt_stores_schema(self, mock_context, sample_task):
        """Test that schema is stored in task properties."""
        mock_context.task_definition.properties["prompt"] = "Enter JSON:"
        mock_context.task_definition.properties["schema"] = {"type": "object"}
        action = PromptTaskAction()

        await action.run(sample_task, mock_context)

        assert sample_task.properties["__schema__"] == {"type": "object"}

    # New tests for enhanced prompt features

    async def test_prompt_number_type_valid(self, mock_context, sample_task):
        """Test number input type with valid input."""
        mock_context.task_definition.properties["prompt"] = "Enter age:"
        mock_context.task_definition.properties["input_type"] = "number"
        sample_task.properties["input"] = "25"
        action = PromptTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is True
        assert result.output["response"] == 25
        assert isinstance(result.output["response"], int)

    async def test_prompt_number_type_float(self, mock_context, sample_task):
        """Test number input type with float input."""
        mock_context.task_definition.properties["prompt"] = "Enter price:"
        mock_context.task_definition.properties["input_type"] = "number"
        sample_task.properties["input"] = "19.99"
        action = PromptTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is True
        assert result.output["response"] == 19.99
        assert isinstance(result.output["response"], float)

    async def test_prompt_number_type_invalid(self, mock_context, sample_task):
        """Test number input type with invalid input."""
        mock_context.task_definition.properties["prompt"] = "Enter age:"
        mock_context.task_definition.properties["input_type"] = "number"
        sample_task.properties["input"] = "not a number"
        action = PromptTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is False
        assert "Invalid number" in result.error

    async def test_prompt_boolean_type_yes(self, mock_context, sample_task):
        """Test boolean input type with 'yes' input."""
        mock_context.task_definition.properties["prompt"] = "Continue?"
        mock_context.task_definition.properties["input_type"] = "boolean"
        sample_task.properties["input"] = "yes"
        action = PromptTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is True
        assert result.output["response"] is True

    async def test_prompt_boolean_type_no(self, mock_context, sample_task):
        """Test boolean input type with 'no' input."""
        mock_context.task_definition.properties["prompt"] = "Continue?"
        mock_context.task_definition.properties["input_type"] = "boolean"
        sample_task.properties["input"] = "no"
        action = PromptTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is True
        assert result.output["response"] is False

    async def test_prompt_boolean_type_invalid(self, mock_context, sample_task):
        """Test boolean input type with invalid input."""
        mock_context.task_definition.properties["prompt"] = "Continue?"
        mock_context.task_definition.properties["input_type"] = "boolean"
        sample_task.properties["input"] = "maybe"
        action = PromptTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is False
        assert "Invalid boolean" in result.error

    async def test_prompt_choice_type_valid(self, mock_context, sample_task):
        """Test choice input type with valid selection."""
        mock_context.task_definition.properties["prompt"] = "Select:"
        mock_context.task_definition.properties["input_type"] = "choice"
        mock_context.task_definition.properties["options"] = ["a", "b", "c"]
        sample_task.properties["input"] = "b"
        action = PromptTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is True
        assert result.output["response"] == "b"

    async def test_prompt_choice_type_invalid(self, mock_context, sample_task):
        """Test choice input type with invalid selection."""
        mock_context.task_definition.properties["prompt"] = "Select:"
        mock_context.task_definition.properties["input_type"] = "choice"
        mock_context.task_definition.properties["options"] = ["a", "b", "c"]
        sample_task.properties["input"] = "d"
        action = PromptTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is False
        assert "Invalid choice" in result.error

    async def test_prompt_choice_with_dict_options(self, mock_context, sample_task):
        """Test choice input type with value/label options."""
        mock_context.task_definition.properties["prompt"] = "Select:"
        mock_context.task_definition.properties["input_type"] = "choice"
        mock_context.task_definition.properties["options"] = [
            {"value": "fast", "label": "Fast"},
            {"value": "slow", "label": "Slow"},
        ]
        sample_task.properties["input"] = "fast"
        action = PromptTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is True
        assert result.output["response"] == "fast"

    async def test_prompt_multi_choice_type(self, mock_context, sample_task):
        """Test multi_choice input type."""
        mock_context.task_definition.properties["prompt"] = "Select multiple:"
        mock_context.task_definition.properties["input_type"] = "multi_choice"
        mock_context.task_definition.properties["options"] = ["a", "b", "c"]
        sample_task.properties["input"] = ["a", "c"]
        action = PromptTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is True
        assert result.output["response"] == ["a", "c"]

    async def test_prompt_multi_choice_single_value(self, mock_context, sample_task):
        """Test multi_choice converts single value to list."""
        mock_context.task_definition.properties["prompt"] = "Select multiple:"
        mock_context.task_definition.properties["input_type"] = "multi_choice"
        mock_context.task_definition.properties["options"] = ["a", "b", "c"]
        sample_task.properties["input"] = "a"
        action = PromptTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is True
        assert result.output["response"] == ["a"]

    async def test_prompt_required_empty_fails(self, mock_context, sample_task):
        """Test required field with empty input fails."""
        mock_context.task_definition.properties["prompt"] = "Enter name:"
        mock_context.task_definition.properties["required"] = True
        sample_task.properties["input"] = ""
        action = PromptTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is False
        assert "required" in result.error.lower()

    async def test_prompt_required_with_value_passes(self, mock_context, sample_task):
        """Test required field with value passes."""
        mock_context.task_definition.properties["prompt"] = "Enter name:"
        mock_context.task_definition.properties["required"] = True
        sample_task.properties["input"] = "John"
        action = PromptTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is True
        assert result.output["response"] == "John"

    async def test_prompt_output_key_stores_value(self, mock_context, sample_task):
        """Test output_key stores value in process properties."""
        mock_context.task_definition.properties["prompt"] = "Enter name:"
        mock_context.task_definition.properties["output_key"] = "user_name"
        sample_task.properties["input"] = "Alice"
        action = PromptTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is True
        mock_context.set_process_property.assert_called_with("user_name", "Alice")

    async def test_prompt_custom_validation_error(self, mock_context, sample_task):
        """Test custom validation error message."""
        mock_context.task_definition.properties["prompt"] = "Enter age:"
        mock_context.task_definition.properties["input_type"] = "number"
        mock_context.task_definition.properties["validation_error"] = "Please enter a valid age"
        sample_task.properties["input"] = "abc"
        action = PromptTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is False
        assert result.error == "Please enter a valid age"

    async def test_prompt_stores_metadata(self, mock_context, sample_task):
        """Test that all metadata is stored in task properties."""
        mock_context.task_definition.properties["prompt"] = "Enter value:"
        mock_context.task_definition.properties["input_type"] = "number"
        mock_context.task_definition.properties["options"] = []
        mock_context.task_definition.properties["help"] = "Enter a number"
        mock_context.task_definition.properties["required"] = True
        action = PromptTaskAction()

        await action.run(sample_task, mock_context)

        assert sample_task.properties["__prompt__"] == "Enter value:"
        assert sample_task.properties["__input_type__"] == "number"
        assert sample_task.properties["__help__"] == "Enter a number"
        assert sample_task.properties["__required__"] is True

    async def test_prompt_invalid_input_type(self, mock_context, sample_task):
        """Test that invalid input_type returns error."""
        mock_context.task_definition.properties["prompt"] = "Enter value:"
        mock_context.task_definition.properties["input_type"] = "invalid_type"
        action = PromptTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is False
        assert "Invalid input_type" in result.error

    async def test_prompt_awaiting_includes_metadata(self, mock_context, sample_task):
        """Test awaiting state includes all metadata."""
        mock_context.task_definition.properties["prompt"] = "Select:"
        mock_context.task_definition.properties["input_type"] = "choice"
        mock_context.task_definition.properties["options"] = ["a", "b"]
        mock_context.task_definition.properties["help"] = "Choose one"
        mock_context.task_definition.properties["required"] = True
        action = PromptTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is True
        assert result.output["awaiting_input"] is True
        assert result.output["input_type"] == "choice"
        assert result.output["options"] == ["a", "b"]
        assert result.output["help"] == "Choose one"
        assert result.output["required"] is True


class TestDecisionTaskAction:
    """Tests for DecisionTaskAction."""

    async def test_decision_with_selection(self, mock_context, sample_task):
        """Test decision with pre-provided selection."""
        sample_task.properties["selection"] = "option_a"
        mock_context.task_definition.properties["prompt"] = "Choose:"
        mock_context.task_definition.properties["options"] = ["option_a", "option_b"]
        action = DecisionTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is True
        assert result.output == "option_a"
        assert result.next_route == "option_a"

    async def test_decision_invalid_selection(self, mock_context, sample_task):
        """Test decision with invalid selection."""
        sample_task.properties["selection"] = "invalid_option"
        mock_context.task_definition.properties["options"] = ["option_a", "option_b"]
        action = DecisionTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is False
        assert "Invalid selection" in result.error

    async def test_decision_with_default(self, mock_context, sample_task):
        """Test decision with default option."""
        mock_context.task_definition.properties["prompt"] = "Choose:"
        mock_context.task_definition.properties["options"] = ["option_a", "option_b"]
        mock_context.task_definition.properties["default"] = "option_b"
        action = DecisionTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is True
        assert result.output == "option_b"
        assert result.next_route == "option_b"

    async def test_decision_awaiting_input(self, mock_context, sample_task):
        """Test decision awaiting input."""
        mock_context.task_definition.properties["prompt"] = "Choose:"
        mock_context.task_definition.properties["options"] = ["a", "b", "c"]
        action = DecisionTaskAction()

        result = await action.run(sample_task, mock_context)

        assert result.success is True
        assert result.output["awaiting_input"] is True
        assert result.output["options"] == ["a", "b", "c"]
        assert sample_task.properties["__options__"] == ["a", "b", "c"]

    async def test_decision_template_resolution(self, mock_context, sample_task):
        """Test template resolution in decision prompt."""
        mock_context.task_definition.properties["prompt"] = "Value is {{var}}, choose:"
        mock_context.task_definition.properties["options"] = ["yes", "no"]
        mock_context.task_definition.properties["default"] = "yes"
        action = DecisionTaskAction()

        result = await action.run(sample_task, mock_context)

        assert sample_task.properties["__prompt__"] == "Value is value, choose:"
