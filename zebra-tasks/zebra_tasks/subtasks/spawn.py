"""SubworkflowAction - Spawn and execute a sub-workflow."""

from typing import Any

from zebra.core.models import (
    ProcessDefinition,
    ProcessInstance,
    TaskInstance,
    TaskResult,
)
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction
from zebra.definitions.loader import load_definition_from_yaml


class SubworkflowAction(TaskAction):
    """
    TaskAction that spawns and executes a sub-workflow.

    This action creates a child process from a workflow definition,
    executes it, and returns the result. The sub-workflow runs as
    a child of the current process, inheriting context.

    Properties:
        workflow: Workflow definition (inline dict, YAML string, or definition ID)
        workflow_file: Path to workflow YAML file (alternative to workflow)
        properties: Properties to pass to the sub-workflow
        wait: Whether to wait for completion (default: True)
        timeout: Timeout in seconds (optional)
        output_key: Where to store result in process properties

    Example workflow usage:
        ```yaml
        tasks:
          run_analysis:
            name: "Run Analysis"
            action: subworkflow
            properties:
              workflow_file: "workflows/analysis.yaml"
              properties:
                input_data: "{{data}}"
              output_key: analysis_result
        ```
    """

    description = "Spawn and execute a sub-workflow as a child process."

    inputs = [
        ParameterDef(
            name="workflow",
            type="any",
            description="Workflow definition (inline dict, YAML string, or definition ID)",
            required=False,
        ),
        ParameterDef(
            name="workflow_file",
            type="string",
            description="Path to workflow YAML file (alternative to workflow)",
            required=False,
        ),
        ParameterDef(
            name="properties",
            type="dict",
            description="Properties to pass to the sub-workflow",
            required=False,
            default={},
        ),
        ParameterDef(
            name="wait",
            type="bool",
            description="Whether to wait for sub-workflow completion",
            required=False,
            default=True,
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
            name="process_id",
            type="string",
            description="ID of the spawned sub-process",
            required=True,
        ),
        ParameterDef(
            name="success",
            type="bool",
            description="Whether the sub-workflow completed successfully (when wait=True)",
            required=False,
        ),
        ParameterDef(
            name="properties",
            type="dict",
            description="Final properties of the sub-workflow (when wait=True)",
            required=False,
        ),
        ParameterDef(
            name="output",
            type="any",
            description="Output from the sub-workflow's __output__ property (when wait=True)",
            required=False,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Execute the sub-workflow."""
        # Get workflow definition
        workflow_def = await self._get_workflow_definition(task, context)
        if workflow_def is None:
            return TaskResult.fail("No workflow definition provided")

        # Get properties to pass to sub-workflow
        sub_properties = task.properties.get("properties", {})
        resolved_properties = {}
        for key, value in sub_properties.items():
            if isinstance(value, str):
                resolved_properties[key] = context.resolve_template(value)
            else:
                resolved_properties[key] = value

        # Inherit parent context
        resolved_properties["__parent_process_id__"] = context.process.id
        resolved_properties["__parent_task_id__"] = task.id

        # Copy over special properties from parent
        for prop_key in context.process.properties:
            if prop_key.startswith("__") and prop_key not in resolved_properties:
                resolved_properties[prop_key] = context.process.properties[prop_key]

        # Create sub-process
        sub_process = await context.engine.create_process(
            workflow_def,
            properties=resolved_properties,
        )

        # Link as child process
        sub_process.parent_process_id = context.process.id
        sub_process.parent_task_id = task.id
        await context.store.save_process(sub_process)

        # Start sub-process
        await context.engine.start_process(sub_process.id)

        # Check if we should wait for completion
        wait = task.properties.get("wait", True)
        if not wait:
            # Return immediately with process ID
            output_key = task.properties.get("output_key", "subworkflow_process_id")
            context.set_process_property(output_key, sub_process.id)
            return TaskResult.ok(output={"process_id": sub_process.id})

        # Wait for completion
        timeout = task.properties.get("timeout")
        result = await self._wait_for_completion(context, sub_process.id, timeout)

        # Store result
        output_key = task.properties.get("output_key", "subworkflow_result")
        context.set_process_property(output_key, result)

        if result.get("success", False):
            return TaskResult.ok(output=result)
        else:
            return TaskResult.fail(result.get("error", "Sub-workflow failed"))

    async def _get_workflow_definition(
        self, task: TaskInstance, context: ExecutionContext
    ) -> ProcessDefinition | None:
        """Get workflow definition from task properties."""
        # Check for inline workflow
        workflow = task.properties.get("workflow")
        if workflow:
            if isinstance(workflow, dict):
                return ProcessDefinition(**workflow)
            elif isinstance(workflow, str):
                # Could be YAML string or definition ID
                if workflow.strip().startswith("name:"):
                    return load_definition_from_yaml(workflow)
                else:
                    # Assume it's a definition ID, load from store
                    return await context.store.get_definition(workflow)
            elif isinstance(workflow, ProcessDefinition):
                return workflow

        # Check for workflow file
        workflow_file = task.properties.get("workflow_file")
        if workflow_file:
            resolved_path = context.resolve_template(workflow_file)
            with open(resolved_path) as f:
                return load_definition_from_yaml(f.read())

        return None

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
            process = await context.store.get_process(process_id)
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
