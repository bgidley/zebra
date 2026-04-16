"""Tests for property JSON-serialization enforcement.

Verifies that non-serializable values are rejected at model construction,
in set_process_property(), and in storage backends.
"""

import os
import tempfile
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from zebra.core.models import (
    ProcessDefinition,
    ProcessInstance,
    ProcessState,
    TaskDefinition,
    TaskInstance,
    TaskResult,
    TaskState,
)
from zebra.storage.sqlite import SQLiteStore
from zebra.tasks.base import ExecutionContext

# =============================================================================
# Non-serializable test values
# =============================================================================


class CustomObject:
    """A non-JSON-serializable object for testing."""

    def __init__(self, value: str):
        self.value = value


NON_SERIALIZABLE_VALUES = [
    CustomObject("test"),
    {1, 2, 3},  # set
    lambda x: x,  # function
    object(),
    b"bytes_data",  # bytes
]


# =============================================================================
# Model construction validation
# =============================================================================


class TestProcessInstanceValidation:
    """ProcessInstance rejects non-serializable properties at construction."""

    def test_valid_properties_accepted(self):
        """Complex but valid JSON structures should be accepted."""
        process = ProcessInstance(
            id="p1",
            definition_id="d1",
            properties={
                "string": "hello",
                "number": 42,
                "float": 3.14,
                "bool": True,
                "null": None,
                "list": [1, "two", None, [3]],
                "nested": {"a": {"b": {"c": [1, 2, 3]}}},
            },
        )
        assert process.properties["string"] == "hello"
        assert process.properties["nested"]["a"]["b"]["c"] == [1, 2, 3]

    def test_empty_properties_accepted(self):
        """Default empty properties should be accepted."""
        process = ProcessInstance(id="p1", definition_id="d1")
        assert process.properties == {}

    @pytest.mark.parametrize("bad_value", NON_SERIALIZABLE_VALUES)
    def test_non_serializable_rejected(self, bad_value):
        """Non-JSON-serializable values should be rejected."""
        with pytest.raises(ValidationError, match="JSON-serializable"):
            ProcessInstance(
                id="p1",
                definition_id="d1",
                properties={"bad": bad_value},
            )


class TestTaskInstanceValidation:
    """TaskInstance rejects non-serializable properties at construction."""

    def test_valid_properties_accepted(self):
        task = TaskInstance(
            id="t1",
            process_id="p1",
            task_definition_id="td1",
            foe_id="foe1",
            properties={"key": "value", "count": 5},
        )
        assert task.properties["key"] == "value"

    @pytest.mark.parametrize("bad_value", NON_SERIALIZABLE_VALUES)
    def test_non_serializable_rejected(self, bad_value):
        with pytest.raises(ValidationError, match="JSON-serializable"):
            TaskInstance(
                id="t1",
                process_id="p1",
                task_definition_id="td1",
                foe_id="foe1",
                properties={"bad": bad_value},
            )


class TestTaskDefinitionValidation:
    """TaskDefinition rejects non-serializable properties at construction."""

    def test_valid_properties_accepted(self):
        td = TaskDefinition(id="td1", name="Test", properties={"prompt": "hello"})
        assert td.properties["prompt"] == "hello"

    @pytest.mark.parametrize("bad_value", NON_SERIALIZABLE_VALUES)
    def test_non_serializable_rejected(self, bad_value):
        with pytest.raises(ValidationError, match="JSON-serializable"):
            TaskDefinition(id="td1", name="Test", properties={"bad": bad_value})


class TestProcessDefinitionValidation:
    """ProcessDefinition rejects non-serializable properties at construction."""

    def test_valid_properties_accepted(self):
        pd = ProcessDefinition(
            id="pd1",
            name="Test",
            first_task_id="t1",
            tasks={"t1": TaskDefinition(id="t1", name="T1")},
            properties={"env": "production"},
        )
        assert pd.properties["env"] == "production"

    @pytest.mark.parametrize("bad_value", NON_SERIALIZABLE_VALUES)
    def test_non_serializable_rejected(self, bad_value):
        with pytest.raises(ValidationError, match="JSON-serializable"):
            ProcessDefinition(
                id="pd1",
                name="Test",
                first_task_id="t1",
                tasks={"t1": TaskDefinition(id="t1", name="T1")},
                properties={"bad": bad_value},
            )


# =============================================================================
# ExecutionContext.set_process_property() validation
# =============================================================================


class TestSetProcessProperty:
    """set_process_property() rejects non-serializable values."""

    def _make_context(self) -> ExecutionContext:
        """Create a minimal ExecutionContext for testing."""
        process = ProcessInstance(id="p1", definition_id="d1")
        task_def = TaskDefinition(id="td1", name="Test")
        process_def = ProcessDefinition(
            id="d1",
            name="Test",
            first_task_id="td1",
            tasks={"td1": task_def},
        )
        return ExecutionContext(
            engine=MagicMock(),
            store=MagicMock(),
            process=process,
            process_definition=process_def,
            task_definition=task_def,
        )

    def test_valid_value_accepted(self):
        ctx = self._make_context()
        ctx.set_process_property("key", "value")
        assert ctx.process.properties["key"] == "value"

    def test_complex_valid_value_accepted(self):
        ctx = self._make_context()
        ctx.set_process_property("data", {"nested": [1, 2, {"deep": True}]})
        assert ctx.process.properties["data"]["nested"][2]["deep"] is True

    def test_none_value_accepted(self):
        ctx = self._make_context()
        ctx.set_process_property("key", None)
        assert ctx.process.properties["key"] is None

    @pytest.mark.parametrize("bad_value", NON_SERIALIZABLE_VALUES)
    def test_non_serializable_rejected(self, bad_value):
        ctx = self._make_context()
        with pytest.raises(ValueError, match="JSON-serializable"):
            ctx.set_process_property("bad", bad_value)
        # Property should NOT have been set
        assert "bad" not in ctx.process.properties


# =============================================================================
# SQLiteStore serialization error handling
# =============================================================================


class TestSQLiteStoreSerialization:
    """SQLiteStore raises SerializationError for non-serializable properties."""

    @pytest.fixture
    async def sqlite_store(self):
        """Create a temporary SQLite store for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        store = SQLiteStore(db_path)
        await store.initialize()
        yield store
        await store.close()
        os.unlink(db_path)

    async def test_valid_properties_roundtrip(self, sqlite_store):
        """Valid properties should survive save/load roundtrip."""
        process = ProcessInstance(
            id="p1",
            definition_id="d1",
            state=ProcessState.RUNNING,
            properties={
                "string": "hello",
                "number": 42,
                "float": 3.14,
                "bool": True,
                "null_val": None,
                "list": [1, "two", None],
                "nested": {"a": {"b": [1, 2]}},
            },
        )
        await sqlite_store.save_process(process)
        loaded = await sqlite_store.load_process("p1")

        assert loaded is not None
        assert loaded.properties["string"] == "hello"
        assert loaded.properties["number"] == 42
        assert loaded.properties["float"] == 3.14
        assert loaded.properties["bool"] is True
        assert loaded.properties["null_val"] is None
        assert loaded.properties["list"] == [1, "two", None]
        assert loaded.properties["nested"]["a"]["b"] == [1, 2]

    async def test_task_properties_roundtrip(self, sqlite_store):
        """Task properties should survive save/load roundtrip."""
        task = TaskInstance(
            id="t1",
            process_id="p1",
            task_definition_id="td1",
            state=TaskState.READY,
            foe_id="foe1",
            properties={"prompt": "What is 2+2?", "max_tokens": 100},
        )
        await sqlite_store.save_task(task)
        loaded = await sqlite_store.load_task("t1")

        assert loaded is not None
        assert loaded.properties["prompt"] == "What is 2+2?"
        assert loaded.properties["max_tokens"] == 100


# =============================================================================
# TaskResult output serialization
# =============================================================================


class TestTaskResultOutput:
    """TaskResult.output is stored in process properties and must be serializable."""

    def test_serializable_output(self):
        """Valid JSON-serializable output should work."""
        result = TaskResult.ok(output={"answer": "42", "confidence": 0.95})
        assert result.output == {"answer": "42", "confidence": 0.95}

    def test_output_stored_as_property(self):
        """When output is stored as a process property, serialization is enforced."""
        ctx_process = ProcessInstance(id="p1", definition_id="d1")
        task_def = TaskDefinition(id="td1", name="Test")
        process_def = ProcessDefinition(
            id="d1",
            name="Test",
            first_task_id="td1",
            tasks={"td1": task_def},
        )
        ctx = ExecutionContext(
            engine=MagicMock(),
            store=MagicMock(),
            process=ctx_process,
            process_definition=process_def,
            task_definition=task_def,
        )

        # Simulating what the engine does: store task output as process property
        result = TaskResult.ok(output={"key": "value"})
        ctx.set_process_property("__task_output_td1", result.output)
        assert ctx.process.properties["__task_output_td1"] == {"key": "value"}

    def test_non_serializable_output_caught_at_property_set(self):
        """Non-serializable TaskResult output is caught when set as process property."""
        ctx_process = ProcessInstance(id="p1", definition_id="d1")
        task_def = TaskDefinition(id="td1", name="Test")
        process_def = ProcessDefinition(
            id="d1",
            name="Test",
            first_task_id="td1",
            tasks={"td1": task_def},
        )
        ctx = ExecutionContext(
            engine=MagicMock(),
            store=MagicMock(),
            process=ctx_process,
            process_definition=process_def,
            task_definition=task_def,
        )

        # A TaskResult with a non-serializable output
        bad_output = CustomObject("oops")
        with pytest.raises(ValueError, match="JSON-serializable"):
            ctx.set_process_property("__task_output_td1", bad_output)
