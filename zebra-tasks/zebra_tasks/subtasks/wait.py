"""WaitForSubworkflowAction - Wait for a previously spawned sub-workflow."""

from typing import Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction


class WaitForSubworkflowAction(TaskAction):
    """
    TaskAction that waits for a previously spawned sub-workflow to complete.

    Use this when you've spawned a sub-workflow with wait=False and need
    to wait for it later, or when waiting for multiple sub-workflows.

    Properties:
        process_id: ID of the sub-process to wait for (or template reference)
        timeout: Timeout in seconds (optional)
        output_key: Where to store result in process properties

    Example workflow usage:
        ```yaml
        tasks:
          spawn_task:
            name: "Spawn Analysis"
            action: subworkflow
            properties:
              workflow_file: "analysis.yaml"
              wait: false
              output_key: analysis_process_id

          do_other_work:
            name: "Do Other Work"
            action: some_action

          wait_for_analysis:
            name: "Wait for Analysis"
            action: wait_subworkflow
            properties:
              process_id: "{{analysis_process_id}}"
              output_key: analysis_result
        ```
    """

    description = "Wait for a previously spawned sub-workflow to complete."

    inputs = [
        ParameterDef(
            name="process_id",
            type="string",
            description="ID of the sub-process to wait for (supports {{var}} templates)",
            required=True,
        ),
        ParameterDef(
            name="timeout",
            type="float",
            description="Timeout in seconds for waiting",
            required=False,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the result",
            required=False,
            default="subworkflow_result",
        ),
    ]

    outputs = [
        ParameterDef(
            name="success",
            type="bool",
            description="Whether the sub-workflow completed successfully",
            required=True,
        ),
        ParameterDef(
            name="process_id",
            type="string",
            description="ID of the completed sub-process",
            required=True,
        ),
        ParameterDef(
            name="properties",
            type="dict",
            description="Final properties of the sub-workflow",
            required=False,
        ),
        ParameterDef(
            name="output",
            type="any",
            description="Output from the sub-workflow's __output__ property",
            required=False,
        ),
        ParameterDef(
            name="error",
            type="string",
            description="Error message if the sub-workflow failed",
            required=False,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Wait for the sub-workflow to complete."""
        # Get process ID
        process_id = task.properties.get("process_id")
        if not process_id:
            return TaskResult.fail("No process_id specified")

        # Resolve template if needed
        if isinstance(process_id, str) and "{{" in process_id:
            process_id = context.resolve_template(process_id)

        # Wait for completion
        timeout = task.properties.get("timeout")
        result = await self._wait_for_completion(context, process_id, timeout)

        # Store result
        output_key = task.properties.get("output_key", "subworkflow_result")
        context.set_process_property(output_key, result)

        if result.get("success", False):
            return TaskResult.ok(output=result)
        else:
            return TaskResult.fail(result.get("error", "Sub-workflow failed"))

    async def _wait_for_completion(
        self,
        context: ExecutionContext,
        process_id: str,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Wait for sub-process to complete."""
        import asyncio

        start_time = asyncio.get_event_loop().time()

        while True:
            # Check timeout
            if timeout:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout:
                    return {
                        "success": False,
                        "error": f"Timeout after {timeout}s",
                        "process_id": process_id,
                    }

            # Get process status
            process = await context.store.load_process(process_id)
            if process is None:
                return {
                    "success": False,
                    "error": "Process not found",
                    "process_id": process_id,
                }

            if process.state.value == "complete":
                return {
                    "success": True,
                    "process_id": process_id,
                    "properties": process.properties,
                    "output": process.properties.get("__output__"),
                }

            if process.state.value == "failed":
                return {
                    "success": False,
                    "error": process.properties.get("__error__", "Process failed"),
                    "process_id": process_id,
                }

            # Wait before checking again
            await asyncio.sleep(0.1)
