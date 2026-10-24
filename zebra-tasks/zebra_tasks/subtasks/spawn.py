"""SubworkflowAction - Spawn and execute a sub-workflow."""

from zebra.core.models import (
    ProcessDefinition,
    TaskInstance,
    TaskResult,
)
from zebra.definitions.loader import load_definition_from_yaml
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.subtasks.common import child_result, start_child


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
        timeout: Seconds the child's inline auto-task run may take (optional)
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
            description="Seconds the child's inline auto-task run may take before it fails",
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
        """Start the sub-workflow; when waiting, suspend on it and collect its result on resume.

        The task suspends on the child (#181) instead of polling it, so it holds nothing
        while the child waits on a human, and survives restarts.
        """
        output_key = task.properties.get("output_key", "subworkflow_result")
        if context.subflow_results is not None:
            result = child_result(context.subflow_results[0])
            context.set_process_property(output_key, result)
            if result["success"]:
                return TaskResult.ok(output=result)
            return TaskResult.fail(result["error"])

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

        # Create the sub-process linked from its first save, so the daemon never
        # takes it for a queued goal (#227)
        sub_process = await context.engine.create_process(
            workflow_def,
            properties=resolved_properties,
            parent_process_id=context.process.id,
            parent_task_id=task.id,
        )

        # Start sub-process; its inline run is bounded by timeout
        await start_child(context, sub_process.id, task.properties.get("timeout"))

        if not task.properties.get("wait", True):
            # Return immediately with process ID
            output_key = task.properties.get("output_key", "subworkflow_process_id")
            context.set_process_property(output_key, sub_process.id)
            return TaskResult.ok(output={"process_id": sub_process.id})

        # The engine re-runs this action with subflow_results once the child is terminal.
        return TaskResult.suspend([sub_process.id])

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
                    return await context.store.load_definition(workflow)
            elif isinstance(workflow, ProcessDefinition):
                return workflow

        # Check for workflow file
        workflow_file = task.properties.get("workflow_file")
        if workflow_file:
            resolved_path = context.resolve_template(workflow_file)

            # Try to resolve via workflow library first (handles relative paths)
            library = context.extras.get("__workflow_library__")
            if library is not None:
                # Check if the library has this workflow by filename

                workflow_path = library.library_path / resolved_path
                if workflow_path.exists():
                    with open(workflow_path) as f:
                        return load_definition_from_yaml(f.read())

            # Fall back to direct file path (absolute or cwd-relative)
            with open(resolved_path) as f:
                return load_definition_from_yaml(f.read())

        return None
