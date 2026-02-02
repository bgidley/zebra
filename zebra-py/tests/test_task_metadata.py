"""Tests for TaskAction metadata and self-description functionality."""

import pytest

from zebra.core.models import TaskInstance, TaskResult, TaskState
from zebra.tasks import ActionMetadata, ParameterDef, TaskAction
from zebra.tasks.base import ExecutionContext


class SimpleAction(TaskAction):
    """A simple action with no metadata for testing defaults."""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        return TaskResult.ok(output="done")


class FullyDocumentedAction(TaskAction):
    """A fully documented action with all metadata."""

    description = "Process input data and produce structured output."

    inputs = [
        ParameterDef(
            name="data",
            type="string",
            description="Input data to process",
            required=True,
        ),
        ParameterDef(
            name="format",
            type="string",
            description="Output format (json, xml, csv)",
            required=False,
            default="json",
        ),
        ParameterDef(
            name="count",
            type="int",
            description="Number of items to return",
            required=False,
            default=10,
        ),
        ParameterDef(
            name="options",
            type="dict",
            description="Additional processing options",
            required=False,
        ),
        ParameterDef(
            name="tags",
            type="list",
            description="Tags to apply",
            required=False,
        ),
        ParameterDef(
            name="enabled",
            type="bool",
            description="Enable processing",
            required=False,
            default=True,
        ),
        ParameterDef(
            name="threshold",
            type="float",
            description="Processing threshold",
            required=False,
            default=0.5,
        ),
    ]

    outputs = [
        ParameterDef(
            name="result",
            type="dict",
            description="Processed result data",
            required=True,
        ),
        ParameterDef(
            name="count",
            type="int",
            description="Number of items in result",
            required=True,
        ),
        ParameterDef(
            name="metadata",
            type="dict",
            description="Processing metadata",
            required=False,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        return TaskResult.ok(
            output={
                "result": {"processed": True},
                "count": 1,
            }
        )


# =============================================================================
# ParameterDef Tests
# =============================================================================


class TestParameterDef:
    """Tests for ParameterDef model."""

    def test_minimal_parameter(self):
        """Test creating a parameter with minimal fields."""
        param = ParameterDef(name="test")
        assert param.name == "test"
        assert param.type == "any"
        assert param.description == ""
        assert param.required is False
        assert param.default is None

    def test_full_parameter(self):
        """Test creating a parameter with all fields."""
        param = ParameterDef(
            name="data",
            type="string",
            description="Input data",
            required=True,
            default="default_value",
        )
        assert param.name == "data"
        assert param.type == "string"
        assert param.description == "Input data"
        assert param.required is True
        assert param.default == "default_value"

    def test_parameter_is_frozen(self):
        """Test that ParameterDef is immutable."""
        param = ParameterDef(name="test")
        with pytest.raises(Exception):  # ValidationError for frozen model
            param.name = "changed"

    def test_parameter_types(self):
        """Test various type specifications."""
        types = ["string", "int", "float", "bool", "list", "dict", "any"]
        for type_str in types:
            param = ParameterDef(name="test", type=type_str)
            assert param.type == type_str

    def test_complex_type_strings(self):
        """Test complex type specifications like list[string]."""
        param = ParameterDef(name="tags", type="list[string]")
        assert param.type == "list[string]"

        param = ParameterDef(name="mapping", type="dict[string, any]")
        assert param.type == "dict[string, any]"


# =============================================================================
# ActionMetadata Tests
# =============================================================================


class TestActionMetadata:
    """Tests for ActionMetadata model."""

    def test_empty_metadata(self):
        """Test creating empty metadata."""
        meta = ActionMetadata()
        assert meta.description == ""
        assert meta.inputs == []
        assert meta.outputs == []

    def test_full_metadata(self):
        """Test creating metadata with all fields."""
        inputs = [
            ParameterDef(name="input1", type="string", required=True),
        ]
        outputs = [
            ParameterDef(name="output1", type="dict", required=True),
        ]
        meta = ActionMetadata(
            description="Test action description",
            inputs=inputs,
            outputs=outputs,
        )
        assert meta.description == "Test action description"
        assert len(meta.inputs) == 1
        assert len(meta.outputs) == 1
        assert meta.inputs[0].name == "input1"
        assert meta.outputs[0].name == "output1"

    def test_metadata_is_frozen(self):
        """Test that ActionMetadata is immutable."""
        meta = ActionMetadata(description="test")
        with pytest.raises(Exception):  # ValidationError for frozen model
            meta.description = "changed"


# =============================================================================
# TaskAction Metadata Tests
# =============================================================================


class TestTaskActionMetadata:
    """Tests for TaskAction metadata functionality."""

    def test_simple_action_defaults(self):
        """Test that an action without metadata has sensible defaults."""
        assert SimpleAction.description == ""
        assert SimpleAction.inputs == []
        assert SimpleAction.outputs == []

    def test_simple_action_get_metadata(self):
        """Test get_metadata() on a simple action."""
        meta = SimpleAction.get_metadata()
        assert isinstance(meta, ActionMetadata)
        assert meta.description == ""
        assert meta.inputs == []
        assert meta.outputs == []

    def test_documented_action_class_attrs(self):
        """Test class attributes on a documented action."""
        assert (
            FullyDocumentedAction.description == "Process input data and produce structured output."
        )
        assert len(FullyDocumentedAction.inputs) == 7
        assert len(FullyDocumentedAction.outputs) == 3

    def test_documented_action_get_metadata(self):
        """Test get_metadata() on a documented action."""
        meta = FullyDocumentedAction.get_metadata()
        assert isinstance(meta, ActionMetadata)
        assert "Process input data" in meta.description
        assert len(meta.inputs) == 7
        assert len(meta.outputs) == 3

        # Verify input parameter details
        input_names = [p.name for p in meta.inputs]
        assert "data" in input_names
        assert "format" in input_names
        assert "count" in input_names

        # Verify required flags
        data_param = next(p for p in meta.inputs if p.name == "data")
        assert data_param.required is True

        format_param = next(p for p in meta.inputs if p.name == "format")
        assert format_param.required is False
        assert format_param.default == "json"

    def test_get_metadata_returns_new_instance(self):
        """Test that get_metadata() returns a new instance each time."""
        meta1 = FullyDocumentedAction.get_metadata()
        meta2 = FullyDocumentedAction.get_metadata()
        # Should be equal but not the same object
        assert meta1 == meta2

    def test_instance_get_metadata(self):
        """Test calling get_metadata() on an instance."""
        action = FullyDocumentedAction()
        meta = action.get_metadata()
        assert meta.description == FullyDocumentedAction.description


# =============================================================================
# Input Validation Tests
# =============================================================================


class TestInputValidation:
    """Tests for validate_inputs() method."""

    def _make_task(self, properties: dict) -> TaskInstance:
        """Helper to create a TaskInstance with given properties."""
        return TaskInstance(
            id="test-task",
            process_id="test-process",
            task_definition_id="test-def",
            foe_id="test-foe",
            state=TaskState.READY,
            properties=properties,
        )

    def test_validate_empty_action(self):
        """Test validation on action with no declared inputs."""
        action = SimpleAction()
        task = self._make_task({"anything": "goes"})
        errors = action.validate_inputs(task)
        assert errors == []

    def test_validate_required_present(self):
        """Test validation passes when required params are present."""
        action = FullyDocumentedAction()
        task = self._make_task({"data": "test data"})
        errors = action.validate_inputs(task)
        assert errors == []

    def test_validate_required_missing(self):
        """Test validation fails when required params are missing."""
        action = FullyDocumentedAction()
        task = self._make_task({})
        errors = action.validate_inputs(task)
        assert len(errors) == 1
        assert "Missing required parameter: data" in errors[0]

    def test_validate_type_string(self):
        """Test string type validation."""
        action = FullyDocumentedAction()
        task = self._make_task({"data": 123})  # Wrong type
        errors = action.validate_inputs(task)
        assert len(errors) == 1
        assert "data" in errors[0]
        assert "expected string" in errors[0]

    def test_validate_type_int(self):
        """Test int type validation."""
        action = FullyDocumentedAction()
        task = self._make_task({"data": "test", "count": "not an int"})
        errors = action.validate_inputs(task)
        assert len(errors) == 1
        assert "count" in errors[0]
        assert "expected int" in errors[0]

    def test_validate_type_float_accepts_int(self):
        """Test that float type accepts int values."""
        action = FullyDocumentedAction()
        task = self._make_task({"data": "test", "threshold": 1})  # int for float param
        errors = action.validate_inputs(task)
        assert errors == []

    def test_validate_type_float(self):
        """Test float type validation."""
        action = FullyDocumentedAction()
        task = self._make_task({"data": "test", "threshold": 0.75})
        errors = action.validate_inputs(task)
        assert errors == []

    def test_validate_type_float_rejects_string(self):
        """Test that float type rejects string."""
        action = FullyDocumentedAction()
        task = self._make_task({"data": "test", "threshold": "high"})
        errors = action.validate_inputs(task)
        assert len(errors) == 1
        assert "threshold" in errors[0]

    def test_validate_type_bool(self):
        """Test bool type validation."""
        action = FullyDocumentedAction()
        task = self._make_task({"data": "test", "enabled": True})
        errors = action.validate_inputs(task)
        assert errors == []

        task = self._make_task({"data": "test", "enabled": "yes"})  # Wrong type
        errors = action.validate_inputs(task)
        assert len(errors) == 1
        assert "enabled" in errors[0]

    def test_validate_type_dict(self):
        """Test dict type validation."""
        action = FullyDocumentedAction()
        task = self._make_task({"data": "test", "options": {"key": "value"}})
        errors = action.validate_inputs(task)
        assert errors == []

        task = self._make_task({"data": "test", "options": "not a dict"})
        errors = action.validate_inputs(task)
        assert len(errors) == 1
        assert "options" in errors[0]

    def test_validate_type_list(self):
        """Test list type validation."""
        action = FullyDocumentedAction()
        task = self._make_task({"data": "test", "tags": ["tag1", "tag2"]})
        errors = action.validate_inputs(task)
        assert errors == []

        task = self._make_task({"data": "test", "tags": "not a list"})
        errors = action.validate_inputs(task)
        assert len(errors) == 1
        assert "tags" in errors[0]

    def test_validate_optional_missing(self):
        """Test that optional params can be missing."""
        action = FullyDocumentedAction()
        task = self._make_task({"data": "test"})  # Only required param
        errors = action.validate_inputs(task)
        assert errors == []

    def test_validate_multiple_errors(self):
        """Test that multiple errors are collected."""

        class MultiRequiredAction(TaskAction):
            inputs = [
                ParameterDef(name="a", type="string", required=True),
                ParameterDef(name="b", type="int", required=True),
                ParameterDef(name="c", type="bool", required=True),
            ]

            async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
                return TaskResult.ok()

        action = MultiRequiredAction()
        task = self._make_task({})
        errors = action.validate_inputs(task)
        assert len(errors) == 3

    def test_validate_any_type(self):
        """Test that 'any' type accepts any value."""

        class AnyTypeAction(TaskAction):
            inputs = [
                ParameterDef(name="value", type="any", required=True),
            ]

            async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
                return TaskResult.ok()

        action = AnyTypeAction()

        # String
        task = self._make_task({"value": "string"})
        assert action.validate_inputs(task) == []

        # Int
        task = self._make_task({"value": 123})
        assert action.validate_inputs(task) == []

        # Dict
        task = self._make_task({"value": {"key": "value"}})
        assert action.validate_inputs(task) == []

        # List
        task = self._make_task({"value": [1, 2, 3]})
        assert action.validate_inputs(task) == []

    def test_validate_unknown_type(self):
        """Test that unknown types skip validation."""

        class UnknownTypeAction(TaskAction):
            inputs = [
                ParameterDef(name="value", type="custom_type", required=True),
            ]

            async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
                return TaskResult.ok()

        action = UnknownTypeAction()
        task = self._make_task({"value": "anything"})
        errors = action.validate_inputs(task)
        assert errors == []

    def test_validate_type_aliases(self):
        """Test type aliases (str/string, integer/int, etc.)."""

        class AliasAction(TaskAction):
            inputs = [
                ParameterDef(name="s", type="str", required=True),
                ParameterDef(name="i", type="integer", required=True),
                ParameterDef(name="n", type="number", required=True),
                ParameterDef(name="b", type="boolean", required=True),
                ParameterDef(name="a", type="array", required=True),
                ParameterDef(name="o", type="object", required=True),
            ]

            async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
                return TaskResult.ok()

        action = AliasAction()
        task = self._make_task(
            {
                "s": "string",
                "i": 42,
                "n": 3.14,
                "b": False,
                "a": [1, 2, 3],
                "o": {"key": "value"},
            }
        )
        errors = action.validate_inputs(task)
        assert errors == []


# =============================================================================
# Serialization Tests
# =============================================================================


class TestMetadataSerialization:
    """Tests for metadata serialization."""

    def test_parameter_def_to_dict(self):
        """Test ParameterDef serializes to dict."""
        param = ParameterDef(
            name="data",
            type="string",
            description="Input data",
            required=True,
            default="default",
        )
        d = param.model_dump()
        assert d == {
            "name": "data",
            "type": "string",
            "description": "Input data",
            "required": True,
            "default": "default",
        }

    def test_action_metadata_to_dict(self):
        """Test ActionMetadata serializes to dict."""
        meta = FullyDocumentedAction.get_metadata()
        d = meta.model_dump()
        assert "description" in d
        assert "inputs" in d
        assert "outputs" in d
        assert len(d["inputs"]) == 7
        assert len(d["outputs"]) == 3

    def test_metadata_to_json(self):
        """Test metadata serializes to JSON."""
        meta = FullyDocumentedAction.get_metadata()
        json_str = meta.model_dump_json()
        assert "Process input data" in json_str
        assert '"name":"data"' in json_str.replace(" ", "")
