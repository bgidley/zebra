"""Tests for core data models."""

import pytest

from zebra.core.models import (
    FlowOfExecution,
    ProcessDefinition,
    ProcessInstance,
    ProcessState,
    RoutingDefinition,
    TaskDefinition,
    TaskInstance,
    TaskResult,
    TaskState,
)


class TestTaskDefinition:
    def test_create_minimal(self):
        task = TaskDefinition(id="task1", name="Test Task")
        assert task.id == "task1"
        assert task.name == "Test Task"
        assert task.auto is True
        assert task.synchronized is False
        assert task.action is None

    def test_create_full(self):
        task = TaskDefinition(
            id="task1",
            name="Test Task",
            auto=False,
            synchronized=True,
            action="shell",
            properties={"command": "echo hello"},
        )
        assert task.auto is False
        assert task.synchronized is True
        assert task.action == "shell"
        assert task.properties["command"] == "echo hello"


class TestRoutingDefinition:
    def test_create_serial(self):
        routing = RoutingDefinition(
            id="r1",
            source_task_id="task1",
            dest_task_id="task2",
        )
        assert routing.parallel is False
        assert routing.condition is None

    def test_create_parallel(self):
        routing = RoutingDefinition(
            id="r1",
            source_task_id="task1",
            dest_task_id="task2",
            parallel=True,
            condition="some_condition",
        )
        assert routing.parallel is True
        assert routing.condition == "some_condition"


class TestProcessDefinition:
    def test_create(self):
        tasks = {
            "start": TaskDefinition(id="start", name="Start"),
            "end": TaskDefinition(id="end", name="End"),
        }
        routings = [
            RoutingDefinition(id="r1", source_task_id="start", dest_task_id="end"),
        ]

        definition = ProcessDefinition(
            id="proc1",
            name="Test Process",
            first_task_id="start",
            tasks=tasks,
            routings=routings,
        )

        assert definition.name == "Test Process"
        assert definition.first_task_id == "start"
        assert len(definition.tasks) == 2
        assert len(definition.routings) == 1

    def test_get_task(self):
        tasks = {
            "start": TaskDefinition(id="start", name="Start"),
        }
        definition = ProcessDefinition(
            id="proc1",
            name="Test",
            first_task_id="start",
            tasks=tasks,
        )

        task = definition.get_task("start")
        assert task.name == "Start"

        with pytest.raises(KeyError):
            definition.get_task("nonexistent")

    def test_get_routings(self):
        tasks = {
            "a": TaskDefinition(id="a", name="A"),
            "b": TaskDefinition(id="b", name="B"),
            "c": TaskDefinition(id="c", name="C"),
        }
        routings = [
            RoutingDefinition(id="r1", source_task_id="a", dest_task_id="b"),
            RoutingDefinition(id="r2", source_task_id="a", dest_task_id="c"),
            RoutingDefinition(id="r3", source_task_id="b", dest_task_id="c"),
        ]

        definition = ProcessDefinition(
            id="proc1",
            name="Test",
            first_task_id="a",
            tasks=tasks,
            routings=routings,
        )

        from_a = definition.get_routings_from("a")
        assert len(from_a) == 2

        to_c = definition.get_routings_to("c")
        assert len(to_c) == 2


class TestProcessInstance:
    def test_create(self):
        process = ProcessInstance(
            id="inst1",
            definition_id="def1",
            state=ProcessState.CREATED,
            properties={"key": "value"},
        )

        assert process.id == "inst1"
        assert process.state == ProcessState.CREATED
        assert process.properties["key"] == "value"


class TestTaskInstance:
    def test_create(self):
        task = TaskInstance(
            id="task1",
            process_id="proc1",
            task_definition_id="def1",
            state=TaskState.READY,
            foe_id="foe1",
        )

        assert task.id == "task1"
        assert task.state == TaskState.READY
        assert task.result is None
        assert task.error is None


class TestTaskResult:
    def test_ok(self):
        result = TaskResult.ok(output={"data": 123})
        assert result.success is True
        assert result.output["data"] == 123
        assert result.error is None

    def test_fail(self):
        result = TaskResult.fail("Something went wrong")
        assert result.success is False
        assert result.error == "Something went wrong"


class TestFlowOfExecution:
    def test_create(self):
        foe = FlowOfExecution(
            id="foe1",
            process_id="proc1",
            parent_foe_id=None,
        )

        assert foe.id == "foe1"
        assert foe.parent_foe_id is None

    def test_with_parent(self):
        foe = FlowOfExecution(
            id="foe2",
            process_id="proc1",
            parent_foe_id="foe1",
        )

        assert foe.parent_foe_id == "foe1"
