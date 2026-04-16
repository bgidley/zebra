"""Base classes for task actions and conditions.

This module defines the abstract interfaces that all task actions and
routing conditions must implement. Corresponds to Java ITaskAction and
IConditionAction interfaces.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel, Field

from zebra.core.models import (
    ProcessDefinition,
    ProcessInstance,
    RoutingDefinition,
    TaskDefinition,
    TaskInstance,
    TaskResult,
)

if TYPE_CHECKING:
    from zebra.core.engine import WorkflowEngine
    from zebra.storage.base import StateStore


# =============================================================================
# Task Action Metadata Models
# =============================================================================


class ParameterDef(BaseModel):
    """Definition of a task action parameter (input or output).

    Used to describe the parameters that a TaskAction accepts as inputs
    or produces as outputs. Enables workflow introspection, documentation
    generation, and runtime validation.

    Attributes:
        name: Parameter name (used as key in task.properties or output dict)
        type: Type hint as string - one of: "string", "int", "float", "bool",
              "list", "dict", "any". Use "list[string]" or "dict[string, any]"
              for more specific collection types.
        description: Human-readable description of the parameter
        required: Whether the parameter is required (for inputs) or always
                  present (for outputs). Defaults to False.
        default: Default value for optional input parameters. None indicates
                 no default (for required params) or that the param may be absent.
    """

    name: str = Field(..., description="Parameter name")
    type: str = Field(
        default="any",
        description="Type hint: string, int, float, bool, list, dict, any",
    )
    description: str = Field(default="", description="Human-readable description")
    required: bool = Field(default=False, description="Whether the parameter is required")
    default: Any = Field(default=None, description="Default value for optional parameters")

    model_config = {"frozen": True}


class ActionMetadata(BaseModel):
    """Metadata describing a TaskAction's interface.

    Provides structured information about what a task action does,
    what inputs it expects, and what outputs it produces. Used for:
    - Workflow introspection and documentation
    - IDE/tool support for workflow authoring
    - Runtime validation of task properties
    - LLM-assisted workflow creation

    Attributes:
        description: What the action does (1-2 sentences)
        inputs: List of input parameters the action accepts
        outputs: List of output parameters the action produces
    """

    description: str = Field(default="", description="What the action does")
    inputs: list[ParameterDef] = Field(
        default_factory=list, description="Input parameters accepted"
    )
    outputs: list[ParameterDef] = Field(
        default_factory=list, description="Output parameters produced"
    )

    model_config = {"frozen": True}


# =============================================================================
# Execution Context
# =============================================================================


@dataclass
class ExecutionContext:
    """Context passed to task actions during execution.

    Provides access to the workflow engine, storage, and related objects
    needed for task execution.

    Attributes:
        engine: The workflow engine instance.
        store: The state store for persistence.
        process: The current process instance.
        process_definition: The process definition.
        task_definition: The current task definition.
        extras: Optional dict for passing arbitrary objects (like memory stores)
            that don't need to be JSON-serializable. Use this for dependency
            injection of services that tasks need but shouldn't be persisted.
    """

    engine: "WorkflowEngine"
    store: "StateStore"
    process: ProcessInstance
    process_definition: ProcessDefinition
    task_definition: TaskDefinition
    extras: dict[str, Any] = field(default_factory=dict)

    def get_task_output(self, task_id: str) -> Any | None:
        """Get the output from a previously completed task.

        Useful for tasks that need to reference results from earlier
        tasks in the workflow.
        """
        return self.process.properties.get(f"__task_output_{task_id}")

    def set_process_property(self, key: str, value: Any) -> None:
        """Set a property on the process instance.

        Properties are persisted to storage and accessible to all subsequent tasks.
        Values must be JSON-serializable (strings, numbers, booleans, lists, dicts,
        and None). Non-serializable values will cause a ValueError immediately, rather
        than failing later during persistence.

        Args:
            key: Property key.
            value: Property value. Must be JSON-serializable.

        Raises:
            ValueError: If the value is not JSON-serializable.
        """
        import json

        try:
            json.dumps(value)
        except (TypeError, ValueError) as e:
            raise ValueError(
                f"Cannot set process property '{key}': value must be JSON-serializable "
                f"(strings, numbers, booleans, lists, dicts, and None). "
                f"Got {type(value).__name__}: {e}"
            ) from e
        self.process.properties[key] = value

    def get_process_property(self, key: str, default: Any = None) -> Any:
        """Get a property from the process instance."""
        return self.process.properties.get(key, default)

    def resolve_template(self, template: str) -> str:
        """Resolve template variables in a string.

        Supports:
        - ``{{property_name}}`` — top-level process property
        - ``{{task_id.output}}`` — legacy task output shorthand
        - ``{{property_name.key}}`` — dict key access on a process property
        - ``{{property_name.key.subkey}}`` — nested dict key access
        """
        import re

        def _dig(obj: object, parts: list[str]) -> object:
            """Walk into obj using successive key lookups."""
            for part in parts:
                if isinstance(obj, dict):
                    obj = obj.get(part)
                else:
                    return None
            return obj

        def replace_var(match: re.Match) -> str:
            var = match.group(1)
            if "." in var:
                parts = var.split(".")
                root, rest = parts[0], parts[1:]

                # Legacy: {{task_id.output}} — kept for backward compatibility
                if len(rest) == 1 and rest[0] == "output":
                    output = self.get_task_output(root)
                    if output is not None:
                        return str(output)

                # Try process property dict navigation: {{prop.key.subkey}}
                prop_value = self.get_process_property(root)
                if prop_value is not None:
                    result = _dig(prop_value, rest)
                    if result is not None:
                        return str(result)

                # Fall back to full var as a flat process property key
                return str(self.get_process_property(var, ""))

            # Simple process property
            return str(self.get_process_property(var, ""))

        # Allow dots and multiple segments in the variable name
        return re.sub(r"\{\{(\w+(?:\.\w+)*)\}\}", replace_var, template)


class TaskAction(ABC):
    """Abstract base class for task actions.

    Implement this interface to create custom task types. The run() method
    is called by the engine when a task is executed.

    Corresponds to Java ITaskAction interface.

    Subclasses should define class-level metadata for self-description:
        - description: What the action does (1-2 sentences)
        - inputs: List of ParameterDef for input parameters
        - outputs: List of ParameterDef for output parameters

    Example:
        class MyCustomAction(TaskAction):
            description = "Perform a custom operation on input data."
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
                    description="Output format",
                    default="json",
                ),
            ]
            outputs = [
                ParameterDef(
                    name="result",
                    type="dict",
                    description="Processed result",
                    required=True,
                ),
            ]

            async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
                # Do something useful
                return TaskResult.ok(output={"result": "done"})
    """

    # Class-level metadata - override in subclasses
    description: ClassVar[str] = ""
    inputs: ClassVar[list[ParameterDef]] = []
    outputs: ClassVar[list[ParameterDef]] = []

    @classmethod
    def get_metadata(cls) -> ActionMetadata:
        """Return structured metadata about this action.

        Returns:
            ActionMetadata with description, inputs, and outputs.
        """
        return ActionMetadata(
            description=cls.description,
            inputs=list(cls.inputs),
            outputs=list(cls.outputs),
        )

    def validate_inputs(self, task: TaskInstance) -> list[str]:
        """Validate task properties against the input schema.

        Checks that all required parameters are present and that
        provided values match expected types where possible.

        Args:
            task: The task instance to validate

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: list[str] = []
        properties = task.properties

        for param in self.inputs:
            value = properties.get(param.name)

            # Check required parameters
            if param.required and value is None:
                errors.append(f"Missing required parameter: {param.name}")
                continue

            # Skip type checking if value is not provided (optional param)
            if value is None:
                continue

            # Type validation
            type_error = self._validate_type(param.name, value, param.type)
            if type_error:
                errors.append(type_error)

        return errors

    def _validate_type(self, name: str, value: Any, expected_type: str) -> str | None:
        """Validate a value against an expected type.

        Args:
            name: Parameter name (for error messages)
            value: The value to check
            expected_type: Expected type string

        Returns:
            Error message if validation fails, None if valid.
        """
        # Handle "any" type - always valid
        if expected_type == "any":
            return None

        # Map type strings to Python types
        type_map: dict[str, type | tuple[type, ...]] = {
            "string": str,
            "str": str,
            "int": int,
            "integer": int,
            "float": (int, float),  # Accept int for float
            "number": (int, float),
            "bool": bool,
            "boolean": bool,
            "list": list,
            "array": list,
            "dict": dict,
            "object": dict,
        }

        # Handle generic list/dict types like "list[string]"
        base_type = expected_type.split("[")[0].lower()

        expected_python_type = type_map.get(base_type)
        if expected_python_type is None:
            # Unknown type - skip validation
            return None

        if not isinstance(value, expected_python_type):
            actual_type = type(value).__name__
            return f"Parameter '{name}' expected {expected_type}, got {actual_type}"

        return None

    @abstractmethod
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Execute the task action.

        Args:
            task: The task instance being executed
            context: Execution context with engine, store, and related objects

        Returns:
            TaskResult indicating success/failure and any output

        Raises:
            Any exception will be caught and converted to a failed TaskResult
        """
        pass

    async def on_construct(self, task: TaskInstance, context: ExecutionContext) -> None:
        """Called before task execution (optional).

        Override this method to perform setup work before the main
        task action runs.
        """
        pass

    async def on_destruct(self, task: TaskInstance, context: ExecutionContext) -> None:
        """Called after task completion (optional).

        Override this method to perform cleanup work after the main
        task action completes (regardless of success/failure).
        """
        pass


class ConditionAction(ABC):
    """Abstract base class for routing conditions.

    Implement this interface to create custom routing conditions.
    The evaluate() method is called to determine if a routing should fire.

    Corresponds to Java IConditionAction interface.

    Example:
        class IsApprovedCondition(ConditionAction):
            async def evaluate(self, routing: RoutingDefinition, task: TaskInstance,
                             context: ExecutionContext) -> bool:
                return task.result.get("approved", False)
    """

    @abstractmethod
    async def evaluate(
        self,
        routing: RoutingDefinition,
        task: TaskInstance,
        context: ExecutionContext,
    ) -> bool:
        """Evaluate whether this routing should fire.

        Args:
            routing: The routing definition being evaluated
            task: The task instance that just completed
            context: Execution context with engine, store, and related objects

        Returns:
            True if the routing should fire, False otherwise
        """
        pass


class AlwaysTrueCondition(ConditionAction):
    """A condition that always returns True. Used as default when no condition specified."""

    async def evaluate(
        self,
        routing: RoutingDefinition,
        task: TaskInstance,
        context: ExecutionContext,
    ) -> bool:
        return True


class RouteNameCondition(ConditionAction):
    """A condition that matches the task result's next_route against the routing name.

    This is useful for decision tasks where the task action determines
    which route to take by setting result.next_route.
    """

    async def evaluate(
        self,
        routing: RoutingDefinition,
        task: TaskInstance,
        context: ExecutionContext,
    ) -> bool:
        if task.result is None:
            return routing.name is None or routing.name == ""

        # If task specified a next_route, only that route fires
        if isinstance(task.result, dict):
            next_route = task.result.get("next_route")
            if next_route is not None:
                return routing.name == next_route

        return True
