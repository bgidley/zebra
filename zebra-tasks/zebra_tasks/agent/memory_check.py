"""MemoryCheckAction - Check if agent memory needs compaction."""

from typing import TYPE_CHECKING

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

if TYPE_CHECKING:
    from zebra_agent.storage.interfaces import MemoryStore


class MemoryCheckAction(TaskAction):
    """
    Check if agent memory needs compaction.

    This action checks the memory store to determine if short-term or
    long-term memory compaction is needed. It sets `next_route` to control
    the workflow routing.

    Properties:
        output_key: Where to store the check result (default: "memory_status")

    Output:
        - needs_short_term: bool - True if short-term memory needs compaction
        - needs_long_term: bool - True if long-term memory needs compaction

    Routes:
        - "compact_short" - If short-term compaction is needed
        - "compact_long" - If only long-term compaction is needed
        - "continue" - If no compaction is needed

    Example workflow usage:
        ```yaml
        tasks:
          check_memory:
            name: "Check Memory Status"
            action: memory_check
            auto: true
            properties:
              output_key: memory_status

        routings:
          - from: check_memory
            to: compact_short_term
            condition: route_name
            name: "compact_short"

          - from: check_memory
            to: compact_long_term
            condition: route_name
            name: "compact_long"

          - from: check_memory
            to: next_task
            condition: route_name
            name: "continue"
        ```
    """

    description = "Check if agent memory needs compaction."

    inputs = [
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the result",
            required=False,
            default="memory_status",
        ),
    ]

    outputs = [
        ParameterDef(
            name="needs_short_term",
            type="bool",
            description="True if short-term memory needs compaction",
            required=True,
        ),
        ParameterDef(
            name="needs_long_term",
            type="bool",
            description="True if long-term memory needs compaction",
            required=True,
        ),
    ]

    def __init__(self, memory_store: "MemoryStore | None" = None):
        """
        Initialize the action.

        Args:
            memory_store: Memory store for checking compaction status.
                         If None, will try to get from IoC container at runtime.
        """
        self.memory_store = memory_store

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Check memory compaction status."""
        output_key = task.properties.get("output_key", "memory_status")

        # Get memory store - try IoC container if not injected
        memory_store = self.memory_store
        if memory_store is None:
            memory_store = context.process.properties.get("__memory_store__")

        if memory_store is None:
            # No memory store available - no compaction needed
            result = {
                "needs_short_term": False,
                "needs_long_term": False,
            }
            context.set_process_property(output_key, result)
            return TaskResult(success=True, output=result, next_route="continue")

        try:
            # Check compaction needs
            needs_short = await memory_store.needs_short_term_compaction()
            needs_long = await memory_store.needs_long_term_compaction()

            result = {
                "needs_short_term": needs_short,
                "needs_long_term": needs_long,
            }

            # Store result
            context.set_process_property(output_key, result)

            # Determine next route
            if needs_short:
                next_route = "compact_short"
            elif needs_long:
                next_route = "compact_long"
            else:
                next_route = "continue"

            return TaskResult(success=True, output=result, next_route=next_route)

        except Exception as e:
            return TaskResult.fail(f"Memory check failed: {str(e)}")
