"""Base classes for task actions and conditions.

This module defines the abstract interfaces that all task actions and
routing conditions must implement. Corresponds to Java ITaskAction and
IConditionAction interfaces.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

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


@dataclass
class ExecutionContext:
    """Context passed to task actions during execution.

    Provides access to the workflow engine, storage, and related objects
    needed for task execution.
    """

    engine: "WorkflowEngine"
    store: "StateStore"
    process: ProcessInstance
    process_definition: ProcessDefinition
    task_definition: TaskDefinition

    def get_task_output(self, task_id: str) -> Any | None:
        """Get the output from a previously completed task.

        Useful for tasks that need to reference results from earlier
        tasks in the workflow.
        """
        return self.process.properties.get(f"__task_output_{task_id}")

    def set_process_property(self, key: str, value: Any) -> None:
        """Set a property on the process instance.

        Properties are persisted and accessible to all subsequent tasks.
        """
        self.process.properties[key] = value

    def get_process_property(self, key: str, default: Any = None) -> Any:
        """Get a property from the process instance."""
        return self.process.properties.get(key, default)

    def resolve_template(self, template: str) -> str:
        """Resolve template variables in a string.

        Supports {{task_id.output}} syntax to reference task outputs
        and {{property_name}} for process properties.
        """
        import re

        def replace_var(match: re.Match) -> str:
            var = match.group(1)
            if "." in var:
                # Task output reference: {{task_id.output}}
                task_id, attr = var.split(".", 1)
                if attr == "output":
                    output = self.get_task_output(task_id)
                    return str(output) if output is not None else ""
            # Process property
            return str(self.get_process_property(var, ""))

        return re.sub(r"\{\{(\w+(?:\.\w+)?)\}\}", replace_var, template)


class TaskAction(ABC):
    """Abstract base class for task actions.

    Implement this interface to create custom task types. The run() method
    is called by the engine when a task is executed.

    Corresponds to Java ITaskAction interface.

    Example:
        class MyCustomAction(TaskAction):
            async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
                # Do something useful
                return TaskResult.ok(output="done")
    """

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
