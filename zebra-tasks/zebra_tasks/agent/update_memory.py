"""UpdateMemoryAction - Add memory entry for completed workflow run."""

from typing import TYPE_CHECKING, Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

if TYPE_CHECKING:
    from zebra_agent.storage.interfaces import MemoryStore


class UpdateMemoryAction(TaskAction):
    """
    Add a memory entry for a completed workflow run.

    This action creates a MemoryEntry record from the run results
    and adds it to the agent's short-term memory.

    Properties:
        run_id: Unique identifier for the run
        goal: The user's original goal
        workflow_name: Name of the workflow that was used
        result_summary: Summary of the result (will be truncated to 500 chars)

    Example workflow usage:
        ```yaml
        tasks:
          update_memory:
            name: "Update Memory"
            action: update_memory
            auto: true
            properties:
              run_id: "{{run_id}}"
              goal: "{{goal}}"
              workflow_name: "{{workflow_name}}"
              result_summary: "{{execution_result.output}}"
        ```
    """

    description = "Add memory entry for completed workflow run."

    inputs = [
        ParameterDef(
            name="run_id",
            type="string",
            description="Unique identifier for the run",
            required=True,
        ),
        ParameterDef(
            name="goal",
            type="string",
            description="The user's original goal",
            required=True,
        ),
        ParameterDef(
            name="workflow_name",
            type="string",
            description="Name of the workflow that was used",
            required=True,
        ),
        ParameterDef(
            name="result_summary",
            type="any",
            description="Summary of the result (string or dict)",
            required=False,
        ),
    ]

    outputs = [
        ParameterDef(
            name="added",
            type="bool",
            description="Whether the memory entry was added successfully",
            required=True,
        ),
    ]

    def __init__(self, memory_store: "MemoryStore | None" = None):
        """
        Initialize the action.

        Args:
            memory_store: Memory store for adding entries.
                         If None, will try to get from IoC container at runtime.
        """
        self.memory_store = memory_store

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Add memory entry for the run."""
        # Import here to avoid circular imports
        from zebra_agent.memory import MemoryEntry

        # Get memory store - try IoC container, then context.extras (engine-level injection)
        memory_store = self.memory_store
        if memory_store is None:
            memory_store = context.extras.get("__memory_store__")

        if memory_store is None:
            # No memory store available - skip but don't fail
            return TaskResult.ok(output={"added": False})

        try:
            # Extract properties
            goal = task.properties.get("goal", "")
            workflow_name = task.properties.get("workflow_name", "unknown")
            result_summary = task.properties.get("result_summary")

            # Resolve templates if needed
            if isinstance(goal, str) and "{{" in goal:
                goal = context.resolve_template(goal)
            if isinstance(workflow_name, str) and "{{" in workflow_name:
                workflow_name = context.resolve_template(workflow_name)

            # Resolve result_summary from execution_result if template-based
            if isinstance(result_summary, str) and "{{execution_result" in result_summary:
                execution_result = context.get_process_property("execution_result", {})
                if isinstance(execution_result, dict):
                    result_summary = execution_result.get("output")

            # Format result summary
            summary_str = self._format_summary(result_summary)

            # Create memory entry
            entry = MemoryEntry.create(
                goal=goal,
                workflow_used=workflow_name,
                result_summary=summary_str,
            )

            # Add to memory
            await memory_store.add_entry(entry)

            return TaskResult.ok(output={"added": True})

        except Exception as e:
            # Don't fail the workflow just because memory update failed
            return TaskResult.ok(
                output={
                    "added": False,
                    "error": str(e),
                }
            )

    def _format_summary(self, result: Any, max_length: int = 500) -> str:
        """Format the result as a summary string, truncated to max_length."""
        if result is None:
            return ""

        if isinstance(result, str):
            summary = result
        elif isinstance(result, dict):
            # Try to extract common result keys
            if "response" in result:
                summary = str(result["response"])
            elif "output" in result:
                summary = str(result["output"])
            elif "result" in result:
                summary = str(result["result"])
            else:
                # JSON-like format
                import json

                try:
                    summary = json.dumps(result, indent=2)
                except (TypeError, ValueError):
                    summary = str(result)
        else:
            summary = str(result)

        # Truncate if too long
        if len(summary) > max_length:
            summary = summary[: max_length - 3] + "..."

        return summary
