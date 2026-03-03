"""Tests for workflow definition loader."""

import pytest

from zebra.core.exceptions import ValidationError
from zebra.definitions.loader import (
    load_definition_from_yaml,
    validate_definition,
)


class TestYAMLLoader:
    def test_load_simple_definition(self):
        yaml_content = """
name: "Test Workflow"
version: 1

tasks:
  start:
    name: "Start Task"
    action: shell
    properties:
      command: "echo hello"

  end:
    name: "End Task"

routings:
  - from: start
    to: end
"""
        definition = load_definition_from_yaml(yaml_content)

        assert definition.name == "Test Workflow"
        assert definition.version == 1
        assert len(definition.tasks) == 2
        assert len(definition.routings) == 1
        assert definition.first_task_id == "start"

    def test_load_with_parallel_routing(self):
        yaml_content = """
name: "Parallel Test"

tasks:
  start:
    name: Start
  branch_a:
    name: Branch A
  branch_b:
    name: Branch B
  join:
    name: Join
    synchronized: true

routings:
  - from: start
    to: branch_a
    parallel: true
  - from: start
    to: branch_b
    parallel: true
  - from: branch_a
    to: join
  - from: branch_b
    to: join
"""
        definition = load_definition_from_yaml(yaml_content)

        assert len(definition.tasks) == 4
        assert definition.tasks["join"].synchronized is True

        parallel_routings = [r for r in definition.routings if r.parallel]
        assert len(parallel_routings) == 2

    def test_load_with_conditions(self):
        yaml_content = """
name: "Conditional Test"

tasks:
  decision:
    name: Decision
  option_a:
    name: Option A
  option_b:
    name: Option B

routings:
  - from: decision
    to: option_a
    name: "yes"
    condition: route_name
  - from: decision
    to: option_b
    name: "no"
    condition: route_name
"""
        definition = load_definition_from_yaml(yaml_content)

        assert len(definition.routings) == 2
        assert definition.routings[0].condition == "route_name"
        assert definition.routings[0].name == "yes"

    def test_shorthand_task_definition(self):
        yaml_content = """
name: "Shorthand Test"

tasks:
  start: "Start Task"
  end: "End Task"

routings:
  - from: start
    to: end
"""
        definition = load_definition_from_yaml(yaml_content)

        assert definition.tasks["start"].name == "Start Task"
        assert definition.tasks["start"].id == "start"

    def test_explicit_first_task(self):
        yaml_content = """
name: "First Task Test"
first_task: second

tasks:
  first:
    name: First
  second:
    name: Second

routings:
  - from: second
    to: first
"""
        definition = load_definition_from_yaml(yaml_content)
        assert definition.first_task_id == "second"

    def test_missing_name_raises_error(self):
        yaml_content = """
tasks:
  start:
    name: Start
"""
        with pytest.raises(ValidationError) as exc_info:
            load_definition_from_yaml(yaml_content)
        assert "name" in str(exc_info.value)

    def test_missing_tasks_raises_error(self):
        yaml_content = """
name: "No Tasks"
"""
        with pytest.raises(ValidationError) as exc_info:
            load_definition_from_yaml(yaml_content)
        assert "tasks" in str(exc_info.value)

    def test_invalid_routing_source_raises_error(self):
        yaml_content = """
name: "Bad Routing"

tasks:
  start:
    name: Start

routings:
  - from: nonexistent
    to: start
"""
        with pytest.raises(ValidationError) as exc_info:
            load_definition_from_yaml(yaml_content)
        assert "nonexistent" in str(exc_info.value)


class TestValidateDefinition:
    def test_valid_definition(self):
        yaml_content = """
name: Valid

tasks:
  start:
    name: Start
  end:
    name: End

routings:
  - from: start
    to: end
"""
        definition = load_definition_from_yaml(yaml_content)
        errors = validate_definition(definition)
        assert len(errors) == 0

    def test_orphaned_task_warning(self):
        yaml_content = """
name: Orphaned

tasks:
  start:
    name: Start
  orphan:
    name: Orphan
  end:
    name: End

routings:
  - from: start
    to: end
"""
        definition = load_definition_from_yaml(yaml_content)
        errors = validate_definition(definition)

        # Should warn about orphan task
        assert any("orphan" in e.lower() for e in errors)

    def test_sync_task_needs_multiple_routes(self):
        yaml_content = """
name: Single Route Sync

tasks:
  start:
    name: Start
  sync:
    name: Sync
    synchronized: true

routings:
  - from: start
    to: sync
"""
        definition = load_definition_from_yaml(yaml_content)
        errors = validate_definition(definition)

        # Should warn about sync task with single incoming route
        assert any("sync" in e.lower() and "multiple" in e.lower() for e in errors)
