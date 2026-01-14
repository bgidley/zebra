"""Additional tests for definition loader coverage."""

import pytest
import tempfile
import os
from pathlib import Path

from zebra.definitions.loader import (
    load_definition,
    load_definition_from_yaml,
    load_definition_from_dict,
    validate_definition,
)
from zebra.core.exceptions import ValidationError
from zebra.core.models import ProcessDefinition, TaskDefinition, RoutingDefinition


class TestLoadDefinitionFromFile:
    """Tests for load_definition from file."""

    def test_load_yaml_file(self):
        """Test loading from .yaml file."""
        yaml_content = """
name: Test Workflow
version: 1
tasks:
  task1:
    name: Task 1
"""
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w") as f:
            f.write(yaml_content)
            f.flush()
            path = f.name

        try:
            definition = load_definition(path)
            assert definition.name == "Test Workflow"
            assert "task1" in definition.tasks
        finally:
            os.unlink(path)

    def test_load_yml_file(self):
        """Test loading from .yml file."""
        yaml_content = """
name: Test Workflow
tasks:
  task1:
    name: Task 1
"""
        with tempfile.NamedTemporaryFile(suffix=".yml", delete=False, mode="w") as f:
            f.write(yaml_content)
            f.flush()
            path = f.name

        try:
            definition = load_definition(path)
            assert definition.name == "Test Workflow"
        finally:
            os.unlink(path)

    def test_load_json_file(self):
        """Test loading from .json file."""
        json_content = '{"name": "Test Workflow", "tasks": {"task1": {"name": "Task 1"}}}'

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            f.write(json_content)
            f.flush()
            path = f.name

        try:
            definition = load_definition(path)
            assert definition.name == "Test Workflow"
        finally:
            os.unlink(path)

    def test_load_unknown_extension_yaml(self):
        """Test loading file with unknown extension (tries YAML first)."""
        yaml_content = """
name: Test Workflow
tasks:
  task1:
    name: Task 1
"""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            f.write(yaml_content)
            f.flush()
            path = f.name

        try:
            definition = load_definition(path)
            assert definition.name == "Test Workflow"
        finally:
            os.unlink(path)

    def test_load_unknown_extension_json(self):
        """Test loading file with unknown extension (falls back to JSON)."""
        # This is valid JSON but invalid YAML (well, it's also valid YAML, so let's use pure JSON)
        json_content = '{"name": "Test Workflow", "tasks": {"task1": {"name": "Task 1"}}}'

        with tempfile.NamedTemporaryFile(suffix=".dat", delete=False, mode="w") as f:
            f.write(json_content)
            f.flush()
            path = f.name

        try:
            definition = load_definition(path)
            assert definition.name == "Test Workflow"
        finally:
            os.unlink(path)

    def test_load_nonexistent_file(self):
        """Test loading non-existent file raises error."""
        with pytest.raises(FileNotFoundError, match="not found"):
            load_definition("/nonexistent/path/to/file.yaml")


class TestLoadDefinitionFromDict:
    """Tests for load_definition_from_dict."""

    def test_missing_name(self):
        """Test error when name is missing."""
        with pytest.raises(ValidationError, match="Missing required field: 'name'"):
            load_definition_from_dict({"tasks": {"t1": {"name": "T1"}}})

    def test_missing_tasks(self):
        """Test error when tasks is missing."""
        with pytest.raises(ValidationError, match="Missing required field: 'tasks'"):
            load_definition_from_dict({"name": "Test"})

    def test_empty_tasks(self):
        """Test error when tasks is empty."""
        with pytest.raises(ValidationError, match="At least one task is required"):
            load_definition_from_dict({"name": "Test", "tasks": {}})

    def test_routing_missing_from(self):
        """Test error when routing is missing 'from'."""
        with pytest.raises(ValidationError, match="missing 'from' field"):
            load_definition_from_dict({
                "name": "Test",
                "tasks": {"t1": {"name": "T1"}},
                "routings": [{"to": "t1"}],
            })

    def test_routing_missing_to(self):
        """Test error when routing is missing 'to'."""
        with pytest.raises(ValidationError, match="missing 'to' field"):
            load_definition_from_dict({
                "name": "Test",
                "tasks": {"t1": {"name": "T1"}},
                "routings": [{"from": "t1"}],
            })

    def test_routing_invalid_dest(self):
        """Test error when routing destination task doesn't exist."""
        with pytest.raises(ValidationError, match="destination task 'nonexistent' not found"):
            load_definition_from_dict({
                "name": "Test",
                "tasks": {"t1": {"name": "T1"}},
                "routings": [{"from": "t1", "to": "nonexistent"}],
            })

    def test_invalid_first_task(self):
        """Test error when first_task doesn't exist."""
        with pytest.raises(ValidationError, match="First task 'nonexistent' not found"):
            load_definition_from_dict({
                "name": "Test",
                "tasks": {"t1": {"name": "T1"}},
                "first_task": "nonexistent",
            })

    def test_task_with_all_properties(self):
        """Test loading task with all properties."""
        definition = load_definition_from_dict({
            "name": "Test",
            "tasks": {
                "t1": {
                    "name": "Task 1",
                    "auto": False,
                    "synchronized": True,
                    "action": "shell",
                    "construct_action": "setup",
                    "destruct_action": "cleanup",
                    "properties": {"cmd": "echo test"},
                }
            },
        })

        task = definition.tasks["t1"]
        assert task.name == "Task 1"
        assert task.auto is False
        assert task.synchronized is True
        assert task.action == "shell"
        assert task.construct_action == "setup"
        assert task.destruct_action == "cleanup"
        assert task.properties == {"cmd": "echo test"}

    def test_definition_with_actions(self):
        """Test loading definition with construct/destruct actions."""
        definition = load_definition_from_dict({
            "name": "Test",
            "tasks": {"t1": {"name": "T1"}},
            "construct_action": "init",
            "destruct_action": "cleanup",
            "properties": {"global": "value"},
        })

        assert definition.construct_action == "init"
        assert definition.destruct_action == "cleanup"
        assert definition.properties == {"global": "value"}

    def test_routing_with_condition_and_name(self):
        """Test routing with condition and name."""
        definition = load_definition_from_dict({
            "name": "Test",
            "tasks": {
                "t1": {"name": "T1"},
                "t2": {"name": "T2"},
            },
            "routings": [{
                "from": "t1",
                "to": "t2",
                "parallel": True,
                "condition": "route_name",
                "name": "approved",
            }],
        })

        routing = definition.routings[0]
        assert routing.parallel is True
        assert routing.condition == "route_name"
        assert routing.name == "approved"


class TestValidateDefinition:
    """Tests for validate_definition."""

    def test_valid_definition(self):
        """Test that valid definition has no errors."""
        definition = ProcessDefinition(
            id="test",
            name="Test",
            version=1,
            first_task_id="t1",
            tasks={
                "t1": TaskDefinition(id="t1", name="T1"),
                "t2": TaskDefinition(id="t2", name="T2"),
            },
            routings=[
                RoutingDefinition(id="r1", source_task_id="t1", dest_task_id="t2"),
            ],
        )

        errors = validate_definition(definition)
        assert len(errors) == 0

    def test_invalid_first_task(self):
        """Test validation catches invalid first task."""
        definition = ProcessDefinition(
            id="test",
            name="Test",
            version=1,
            first_task_id="nonexistent",
            tasks={"t1": TaskDefinition(id="t1", name="T1")},
            routings=[],
        )

        errors = validate_definition(definition)
        assert any("First task" in e for e in errors)

    def test_invalid_routing_source(self):
        """Test validation catches invalid routing source."""
        definition = ProcessDefinition(
            id="test",
            name="Test",
            version=1,
            first_task_id="t1",
            tasks={"t1": TaskDefinition(id="t1", name="T1")},
            routings=[
                RoutingDefinition(id="r1", source_task_id="nonexistent", dest_task_id="t1"),
            ],
        )

        errors = validate_definition(definition)
        assert any("source" in e for e in errors)

    def test_invalid_routing_dest(self):
        """Test validation catches invalid routing destination."""
        definition = ProcessDefinition(
            id="test",
            name="Test",
            version=1,
            first_task_id="t1",
            tasks={"t1": TaskDefinition(id="t1", name="T1")},
            routings=[
                RoutingDefinition(id="r1", source_task_id="t1", dest_task_id="nonexistent"),
            ],
        )

        errors = validate_definition(definition)
        assert any("destination" in e for e in errors)
