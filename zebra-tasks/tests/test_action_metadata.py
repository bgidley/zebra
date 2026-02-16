"""Tests for task action metadata across all zebra-tasks actions."""

import pytest

from zebra.tasks import ActionMetadata, ParameterDef

# Import all actions from zebra-tasks
from zebra_tasks.llm.action import LLMCallAction
from zebra_tasks.subtasks.spawn import SubworkflowAction
from zebra_tasks.subtasks.wait import WaitForSubworkflowAction
from zebra_tasks.subtasks.parallel import ParallelSubworkflowsAction
from zebra_tasks.filesystem.read import FileReadAction
from zebra_tasks.filesystem.write import FileWriteAction
from zebra_tasks.filesystem.copy import FileCopyAction
from zebra_tasks.filesystem.move import FileMoveAction
from zebra_tasks.filesystem.delete import FileDeleteAction
from zebra_tasks.filesystem.search import FileSearchAction
from zebra_tasks.filesystem.info import FileExistsAction, FileInfoAction, DirectoryListAction
from zebra_tasks.compute.python_exec import PythonExecAction
from zebra_tasks.agent.analyzer import MetricsAnalyzerAction
from zebra_tasks.agent.evaluator import WorkflowEvaluatorAction
from zebra_tasks.agent.optimizer import WorkflowOptimizerAction
from zebra_tasks.agent.creator import WorkflowCreatorAction
from zebra_tasks.agent.selector import WorkflowSelectorAction


# All actions to test
ALL_ACTIONS = [
    # LLM
    LLMCallAction,
    # Subtasks
    SubworkflowAction,
    WaitForSubworkflowAction,
    ParallelSubworkflowsAction,
    # Filesystem
    FileReadAction,
    FileWriteAction,
    FileCopyAction,
    FileMoveAction,
    FileDeleteAction,
    FileSearchAction,
    FileExistsAction,
    FileInfoAction,
    DirectoryListAction,
    # Compute
    PythonExecAction,
    # Agent
    MetricsAnalyzerAction,
    WorkflowEvaluatorAction,
    WorkflowOptimizerAction,
    WorkflowCreatorAction,
    WorkflowSelectorAction,
]


class TestAllActionsHaveMetadata:
    """Test that all actions have proper metadata defined."""

    @pytest.mark.parametrize("action_class", ALL_ACTIONS)
    def test_action_has_description(self, action_class):
        """Test that action has a non-empty description."""
        assert action_class.description, f"{action_class.__name__} has no description"
        assert len(action_class.description) > 10, f"{action_class.__name__} description too short"

    @pytest.mark.parametrize("action_class", ALL_ACTIONS)
    def test_action_has_inputs(self, action_class):
        """Test that action has inputs defined (can be empty list)."""
        assert isinstance(action_class.inputs, list), f"{action_class.__name__} inputs not a list"

    @pytest.mark.parametrize("action_class", ALL_ACTIONS)
    def test_action_has_outputs(self, action_class):
        """Test that action has outputs defined (can be empty list)."""
        assert isinstance(action_class.outputs, list), f"{action_class.__name__} outputs not a list"

    @pytest.mark.parametrize("action_class", ALL_ACTIONS)
    def test_get_metadata_returns_valid_metadata(self, action_class):
        """Test that get_metadata() returns a valid ActionMetadata."""
        meta = action_class.get_metadata()
        assert isinstance(meta, ActionMetadata)
        assert meta.description == action_class.description
        assert len(meta.inputs) == len(action_class.inputs)
        assert len(meta.outputs) == len(action_class.outputs)


class TestInputParameterValidation:
    """Test input parameter definitions."""

    @pytest.mark.parametrize("action_class", ALL_ACTIONS)
    def test_inputs_are_parameter_defs(self, action_class):
        """Test that all inputs are ParameterDef instances."""
        for param in action_class.inputs:
            assert isinstance(param, ParameterDef), (
                f"{action_class.__name__} has non-ParameterDef input: {param}"
            )

    @pytest.mark.parametrize("action_class", ALL_ACTIONS)
    def test_inputs_have_required_fields(self, action_class):
        """Test that all inputs have name and description."""
        for param in action_class.inputs:
            assert param.name, f"{action_class.__name__} has input without name"
            assert param.description, f"{action_class.__name__}.{param.name} has no description"

    @pytest.mark.parametrize("action_class", ALL_ACTIONS)
    def test_inputs_have_valid_types(self, action_class):
        """Test that all inputs have valid type strings."""
        valid_base_types = {
            "string",
            "str",
            "int",
            "integer",
            "float",
            "number",
            "bool",
            "boolean",
            "list",
            "array",
            "dict",
            "object",
            "any",
        }

        for param in action_class.inputs:
            # Get base type (before any brackets)
            base_type = param.type.split("[")[0].lower()
            assert base_type in valid_base_types, (
                f"{action_class.__name__}.{param.name} has invalid type: {param.type}"
            )


class TestOutputParameterValidation:
    """Test output parameter definitions."""

    @pytest.mark.parametrize("action_class", ALL_ACTIONS)
    def test_outputs_are_parameter_defs(self, action_class):
        """Test that all outputs are ParameterDef instances."""
        for param in action_class.outputs:
            assert isinstance(param, ParameterDef), (
                f"{action_class.__name__} has non-ParameterDef output: {param}"
            )

    @pytest.mark.parametrize("action_class", ALL_ACTIONS)
    def test_outputs_have_required_fields(self, action_class):
        """Test that all outputs have name and description."""
        for param in action_class.outputs:
            assert param.name, f"{action_class.__name__} has output without name"
            assert param.description, f"{action_class.__name__}.{param.name} has no description"


class TestSpecificActionMetadata:
    """Test specific action metadata for correctness."""

    def test_llm_call_action_metadata(self):
        """Test LLMCallAction has expected metadata."""
        meta = LLMCallAction.get_metadata()

        # Check description
        assert "LLM" in meta.description

        # Check key inputs
        input_names = [p.name for p in meta.inputs]
        assert "prompt" in input_names
        assert "temperature" in input_names
        assert "max_tokens" in input_names

        # Check key outputs
        output_names = [p.name for p in meta.outputs]
        assert "response" in output_names
        assert "tokens_used" in output_names

    def test_file_read_action_metadata(self):
        """Test FileReadAction has expected metadata."""
        meta = FileReadAction.get_metadata()

        # Check key inputs
        input_names = [p.name for p in meta.inputs]
        assert "path" in input_names
        assert "encoding" in input_names

        # Check path is required
        path_param = next(p for p in meta.inputs if p.name == "path")
        assert path_param.required is True

        # Check key outputs
        output_names = [p.name for p in meta.outputs]
        assert "content" in output_names
        assert "size" in output_names

    def test_subworkflow_action_metadata(self):
        """Test SubworkflowAction has expected metadata."""
        meta = SubworkflowAction.get_metadata()

        # Check description
        assert (
            "sub-workflow" in meta.description.lower() or "subworkflow" in meta.description.lower()
        )

        # Check key inputs
        input_names = [p.name for p in meta.inputs]
        assert "workflow" in input_names or "workflow_file" in input_names
        assert "wait" in input_names

        # Check key outputs
        output_names = [p.name for p in meta.outputs]
        assert "process_id" in output_names

    def test_python_exec_action_metadata(self):
        """Test PythonExecAction has expected metadata."""
        meta = PythonExecAction.get_metadata()

        # Check description
        assert "python" in meta.description.lower() or "execute" in meta.description.lower()

        # Check key inputs
        input_names = [p.name for p in meta.inputs]
        assert "code" in input_names

        # Code should be required
        code_param = next(p for p in meta.inputs if p.name == "code")
        assert code_param.required is True

        # Check key outputs
        output_names = [p.name for p in meta.outputs]
        assert "result" in output_names
        assert "stdout" in output_names


class TestMetadataSerialization:
    """Test that metadata can be serialized."""

    @pytest.mark.parametrize("action_class", ALL_ACTIONS)
    def test_metadata_to_dict(self, action_class):
        """Test that metadata can be converted to dict."""
        meta = action_class.get_metadata()
        d = meta.model_dump()

        assert isinstance(d, dict)
        assert "description" in d
        assert "inputs" in d
        assert "outputs" in d
        assert isinstance(d["inputs"], list)
        assert isinstance(d["outputs"], list)

    @pytest.mark.parametrize("action_class", ALL_ACTIONS)
    def test_metadata_to_json(self, action_class):
        """Test that metadata can be serialized to JSON."""
        meta = action_class.get_metadata()
        json_str = meta.model_dump_json()

        assert isinstance(json_str, str)
        assert len(json_str) > 0

        # Should be valid JSON (no exception means valid)
        import json

        data = json.loads(json_str)
        assert isinstance(data, dict)


class TestValidateInputs:
    """Test the validate_inputs method on actions."""

    def test_file_read_validates_required_path(self):
        """Test FileReadAction validates required path."""
        from zebra.core.models import TaskInstance, TaskState

        action = FileReadAction()

        # Without path - should fail
        task = TaskInstance(
            id="test",
            process_id="proc",
            task_definition_id="def",
            foe_id="foe",
            state=TaskState.READY,
            properties={},
        )
        errors = action.validate_inputs(task)
        assert len(errors) == 1
        assert "path" in errors[0]

        # With path - should pass
        task = TaskInstance(
            id="test",
            process_id="proc",
            task_definition_id="def",
            foe_id="foe",
            state=TaskState.READY,
            properties={"path": "/some/file.txt"},
        )
        errors = action.validate_inputs(task)
        assert errors == []

    def test_llm_call_validates_types(self):
        """Test LLMCallAction validates parameter types."""
        from zebra.core.models import TaskInstance, TaskState

        action = LLMCallAction()

        # temperature should be float
        task = TaskInstance(
            id="test",
            process_id="proc",
            task_definition_id="def",
            foe_id="foe",
            state=TaskState.READY,
            properties={"temperature": "not a number"},
        )
        errors = action.validate_inputs(task)
        assert len(errors) == 1
        assert "temperature" in errors[0]

        # Valid temperature
        task = TaskInstance(
            id="test",
            process_id="proc",
            task_definition_id="def",
            foe_id="foe",
            state=TaskState.READY,
            properties={"temperature": 0.7},
        )
        errors = action.validate_inputs(task)
        assert errors == []
