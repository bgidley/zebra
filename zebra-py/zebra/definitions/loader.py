"""YAML/JSON workflow definition loader.

This module provides functions for loading workflow definitions from
YAML or JSON files into ProcessDefinition objects.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from zebra.core.exceptions import ValidationError
from zebra.core.models import ProcessDefinition, RoutingDefinition, TaskDefinition


def load_definition(path: str | Path) -> ProcessDefinition:
    """Load a workflow definition from a file.

    Supports both YAML (.yaml, .yml) and JSON (.json) formats.

    Args:
        path: Path to the definition file

    Returns:
        ProcessDefinition object

    Raises:
        FileNotFoundError: If the file doesn't exist
        ValidationError: If the definition is invalid
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Definition file not found: {path}")

    content = path.read_text()

    if path.suffix in {".yaml", ".yml"}:
        data = yaml.safe_load(content)
    elif path.suffix == ".json":
        data = json.loads(content)
    else:
        # Try YAML first, then JSON
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError:
            data = json.loads(content)

    return load_definition_from_dict(data, source=str(path))


def load_definition_from_yaml(yaml_content: str, source: str = "inline") -> ProcessDefinition:
    """Load a workflow definition from a YAML string.

    Args:
        yaml_content: YAML string containing the definition
        source: Optional source identifier for error messages

    Returns:
        ProcessDefinition object

    Raises:
        ValidationError: If the definition is invalid
    """
    data = yaml.safe_load(yaml_content)
    return load_definition_from_dict(data, source=source)


def load_definition_from_dict(data: dict[str, Any], source: str = "dict") -> ProcessDefinition:
    """Load a workflow definition from a dictionary.

    Expected format:
    ```yaml
    name: "My Workflow"
    version: 1

    tasks:
      task_id:
        name: "Task Name"
        action: action_name
        auto: true
        synchronized: false
        properties:
          key: value

    routings:
      - from: task_id_1
        to: task_id_2
        parallel: false
        condition: condition_name
    ```

    Args:
        data: Dictionary containing the definition
        source: Optional source identifier for error messages

    Returns:
        ProcessDefinition object

    Raises:
        ValidationError: If the definition is invalid
    """
    errors: list[str] = []

    # Required fields
    if "name" not in data:
        errors.append("Missing required field: 'name'")
    if "tasks" not in data:
        errors.append("Missing required field: 'tasks'")

    if errors:
        raise ValidationError(f"Invalid definition from {source}: {'; '.join(errors)}")

    name = data["name"]
    version = data.get("version", 1)

    # Generate ID from name and version
    definition_id = _generate_id(name, version)

    # Parse tasks
    tasks: dict[str, TaskDefinition] = {}
    task_data = data.get("tasks", {})

    for task_id, task_info in task_data.items():
        if isinstance(task_info, str):
            # Shorthand: just a name
            task_info = {"name": task_info}

        tasks[task_id] = TaskDefinition(
            id=task_id,
            name=task_info.get("name", task_id),
            auto=task_info.get("auto", True),
            synchronized=task_info.get("synchronized", False),
            action=task_info.get("action"),
            construct_action=task_info.get("construct_action"),
            destruct_action=task_info.get("destruct_action"),
            properties=task_info.get("properties", {}),
        )

    if not tasks:
        errors.append("At least one task is required")

    # Parse routings
    routings: list[RoutingDefinition] = []
    routing_data = data.get("routings", [])

    for i, routing_info in enumerate(routing_data):
        source_task = routing_info.get("from")
        dest_task = routing_info.get("to")

        if not source_task:
            errors.append(f"Routing {i}: missing 'from' field")
            continue
        if not dest_task:
            errors.append(f"Routing {i}: missing 'to' field")
            continue
        if source_task not in tasks:
            errors.append(f"Routing {i}: source task '{source_task}' not found")
        if dest_task not in tasks:
            errors.append(f"Routing {i}: destination task '{dest_task}' not found")

        routing_id = f"{source_task}_to_{dest_task}_{i}"

        routings.append(
            RoutingDefinition(
                id=routing_id,
                source_task_id=source_task,
                dest_task_id=dest_task,
                parallel=routing_info.get("parallel", False),
                condition=routing_info.get("condition"),
                name=routing_info.get("name"),
            )
        )

    # Determine first task
    first_task_id = data.get("first_task")
    if not first_task_id:
        # Default to first task in definition
        first_task_id = next(iter(tasks.keys())) if tasks else None

    if first_task_id and first_task_id not in tasks:
        errors.append(f"First task '{first_task_id}' not found in tasks")

    if errors:
        raise ValidationError(f"Invalid definition from {source}: {'; '.join(errors)}")

    return ProcessDefinition(
        id=definition_id,
        name=name,
        version=version,
        first_task_id=first_task_id,
        tasks=tasks,
        routings=routings,
        construct_action=data.get("construct_action"),
        destruct_action=data.get("destruct_action"),
        properties=data.get("properties", {}),
    )


def validate_definition(definition: ProcessDefinition) -> list[str]:
    """Validate a process definition for common issues.

    Checks:
    - All routing references exist
    - First task exists
    - No orphaned tasks (tasks with no incoming routes except first)
    - Sync tasks have incoming routes

    Args:
        definition: The definition to validate

    Returns:
        List of validation error messages (empty if valid)
    """
    errors: list[str] = []

    # Check first task exists
    if definition.first_task_id not in definition.tasks:
        errors.append(f"First task '{definition.first_task_id}' not found")

    # Check routing references
    for routing in definition.routings:
        if routing.source_task_id not in definition.tasks:
            errors.append(f"Routing source '{routing.source_task_id}' not found")
        if routing.dest_task_id not in definition.tasks:
            errors.append(f"Routing destination '{routing.dest_task_id}' not found")

    # Check for orphaned tasks
    tasks_with_incoming: set[str] = {definition.first_task_id}
    for routing in definition.routings:
        tasks_with_incoming.add(routing.dest_task_id)

    for task_id in definition.tasks:
        if task_id not in tasks_with_incoming:
            errors.append(f"Task '{task_id}' has no incoming routes and is not the first task")

    # Check sync tasks have incoming routes
    for task_id, task_def in definition.tasks.items():
        if task_def.synchronized:
            incoming = definition.get_routings_to(task_id)
            if len(incoming) < 2:
                errors.append(
                    f"Synchronized task '{task_id}' should have multiple incoming routes"
                )

    return errors


def _generate_id(name: str, version: int) -> str:
    """Generate a unique ID from name and version."""
    content = f"{name}:{version}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]
