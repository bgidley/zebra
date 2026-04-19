"""Tests for property JSON-serialization enforcement.

Verifies that non-serializable values are rejected at model construction,
in set_process_property(), and in storage backends.
"""

from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from zebra.core.exceptions import SerializationError
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
# Shared fixtures
# =============================================================================


@pytest.fixture
async def sqlite_store(tmp_path):
    """Create a temporary SQLite store for testing.

    Uses pytest's ``tmp_path`` fixture for automatic cleanup.
    """
    store = SQLiteStore(str(tmp_path / "test.db"))
    await store.initialize()
    yield store
    await store.close()


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

    @pytest.mark.parametrize("bad_value", NON_SERIALIZABLE_VALUES)
    async def test_save_process_raises_serialization_error(self, sqlite_store, bad_value):
        """SQLiteStore.save_process() raises SerializationError for non-serializable values.

        Model construction validators normally block such values, so to exercise
        the storage-layer guard we construct with a valid dict then mutate the
        properties to inject a non-serializable value — mirroring what could
        happen if a task action bypassed ``set_process_property`` and mutated
        ``process.properties`` directly.
        """
        process = ProcessInstance(
            id="p1",
            definition_id="d1",
            state=ProcessState.RUNNING,
            properties={"placeholder": "ok"},
        )
        # Bypass model validation: mutate properties post-construction.
        process.properties["bad"] = bad_value

        with pytest.raises(SerializationError, match="JSON-serializable"):
            await sqlite_store.save_process(process)

    @pytest.mark.parametrize("bad_value", NON_SERIALIZABLE_VALUES)
    async def test_save_task_raises_serialization_error(self, sqlite_store, bad_value):
        """SQLiteStore.save_task() raises SerializationError for non-serializable values."""
        task = TaskInstance(
            id="t1",
            process_id="p1",
            task_definition_id="td1",
            state=TaskState.READY,
            foe_id="foe1",
            properties={"placeholder": "ok"},
        )
        task.properties["bad"] = bad_value

        with pytest.raises(SerializationError, match="JSON-serializable"):
            await sqlite_store.save_task(task)


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


# =============================================================================
# TaskResult JSON round-trip
# =============================================================================


class TestTaskResultRoundTrip:
    """TaskResult survives JSON serialization/deserialization without loss.

    TaskResult crosses serialization boundaries in two places:
      1. Its ``output`` is copied into process properties and persisted.
      2. The full TaskResult is emitted/consumed over transport layers
         (e.g. subtask results, MCP tool responses, API payloads).

    Round-trip fidelity of every field — ``success``, ``output``, ``error``,
    ``next_route`` — is therefore part of the engine contract.
    """

    def _roundtrip(self, result: TaskResult) -> TaskResult:
        """Serialize to JSON string and re-parse, returning the new instance."""
        return TaskResult.model_validate_json(result.model_dump_json())

    def test_ok_result_minimal_roundtrip(self):
        """TaskResult.ok() with no output survives JSON round-trip."""
        original = TaskResult.ok()
        restored = self._roundtrip(original)
        assert restored.success is True
        assert restored.output is None
        assert restored.error is None
        assert restored.next_route is None
        assert restored == original

    def test_fail_result_roundtrip(self):
        """TaskResult.fail() preserves error and success=False."""
        original = TaskResult.fail("boom: something went wrong")
        restored = self._roundtrip(original)
        assert restored.success is False
        assert restored.error == "boom: something went wrong"
        assert restored.output is None
        assert restored.next_route is None
        assert restored == original

    @pytest.mark.parametrize(
        "output",
        [
            "plain string",
            "",
            0,
            42,
            -17,
            3.14,
            0.0,
            True,
            False,
            None,
            [],
            [1, 2, 3],
            ["a", None, 1, 2.5, True],
            {},
            {"answer": 42, "confidence": 0.95},
            {"nested": {"a": {"b": {"c": [1, 2, 3]}}}},
            {"mixed": [{"k": "v"}, None, [1, [2, [3]]]]},
        ],
        ids=[
            "str",
            "empty_str",
            "zero",
            "int",
            "neg_int",
            "float",
            "zero_float",
            "true",
            "false",
            "none",
            "empty_list",
            "int_list",
            "mixed_list",
            "empty_dict",
            "flat_dict",
            "deep_nested_dict",
            "complex_mixed",
        ],
    )
    def test_output_types_roundtrip(self, output):
        """Every JSON-representable output type round-trips byte-for-byte."""
        original = TaskResult.ok(output=output)
        restored = self._roundtrip(original)
        assert restored.success is True
        assert restored.output == output
        assert restored == original

    def test_next_route_roundtrip(self):
        """next_route field survives round-trip (used for conditional routing)."""
        original = TaskResult(
            success=True,
            output={"decision": "approved"},
            next_route="approved",
        )
        restored = self._roundtrip(original)
        assert restored.next_route == "approved"
        assert restored.output == {"decision": "approved"}
        assert restored == original

    def test_all_fields_populated_roundtrip(self):
        """A TaskResult with every field set round-trips with full fidelity."""
        original = TaskResult(
            success=False,
            output={"partial": [1, 2]},
            error="completed with warnings",
            next_route="retry",
        )
        restored = self._roundtrip(original)
        assert restored.success is False
        assert restored.output == {"partial": [1, 2]}
        assert restored.error == "completed with warnings"
        assert restored.next_route == "retry"
        assert restored == original

    def test_model_dump_roundtrip_via_dict(self):
        """model_dump() -> model_validate() round-trip (no JSON string)."""
        original = TaskResult.ok(output={"list": [1, 2, 3], "nested": {"k": "v"}})
        dumped = original.model_dump()
        restored = TaskResult.model_validate(dumped)
        assert restored == original

    def test_roundtrip_preserves_numeric_types(self):
        """int stays int and float stays float through JSON round-trip."""
        original = TaskResult.ok(output={"count": 5, "ratio": 0.5})
        restored = self._roundtrip(original)
        assert restored.output["count"] == 5
        assert isinstance(restored.output["count"], int)
        assert restored.output["ratio"] == 0.5
        assert isinstance(restored.output["ratio"], float)

    def test_roundtrip_preserves_unicode(self):
        """Non-ASCII strings in output survive JSON round-trip."""
        original = TaskResult.ok(
            output={"text": "héllo wörld 🦓 中文", "emoji": "✅"},
        )
        restored = self._roundtrip(original)
        assert restored.output["text"] == "héllo wörld 🦓 中文"
        assert restored.output["emoji"] == "✅"

    async def test_roundtrip_via_sqlite_store(self, sqlite_store):
        """TaskResult.output stored as process property survives SQLite persistence.

        This is the primary production path: the engine stores
        ``__task_output_<task_def_id>`` into process properties, the store
        serializes to JSON, and downstream tasks read it back.
        """
        result = TaskResult.ok(
            output={
                "answer": 42,
                "items": [1, "two", None, {"deep": True}],
                "ratio": 0.75,
            },
        )
        process = ProcessInstance(
            id="p1",
            definition_id="d1",
            state=ProcessState.RUNNING,
            properties={"__task_output_td1": result.output},
        )
        await sqlite_store.save_process(process)
        loaded = await sqlite_store.load_process("p1")

        assert loaded is not None
        assert loaded.properties["__task_output_td1"] == result.output
