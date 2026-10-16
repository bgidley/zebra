"""WaitForSubworkflowAction - Wait for a previously spawned sub-workflow."""

import logging

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.subtasks.common import child_result

logger = logging.getLogger(__name__)


class WaitForSubworkflowAction(TaskAction):
    """
    TaskAction that waits for a previously spawned sub-workflow to complete.

    Use this when you've spawned a sub-workflow with wait=False and need
    to wait for it later, or when waiting for multiple sub-workflows.

    Properties:
        process_id: ID of a sub-process of this process (or template reference)
        timeout: Ignored; bound the child where it is started (subworkflow ``timeout``)
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
            description="Ignored (#181): set timeout on the subworkflow that starts the child",
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
        """Suspend on the sub-workflow and collect its result on resume (#181)."""
        output_key = task.properties.get("output_key", "subworkflow_result")
        if context.subflow_results is not None:
            result = child_result(context.subflow_results[0])
            context.set_process_property(output_key, result)
            if result["success"]:
                return TaskResult.ok(output=result)
            return TaskResult.fail(result["error"])

        # Get process ID
        process_id = task.properties.get("process_id")
        if not process_id:
            return TaskResult.fail("No process_id specified")

        # Resolve template if needed
        if isinstance(process_id, str) and "{{" in process_id:
            process_id = context.resolve_template(process_id)

        process = await context.store.load_process(process_id)
        if process is None:
            return TaskResult.fail(f"Process not found: {process_id}")
        # Only a child's end resumes this task, so an unrelated process can't be waited on.
        if process.parent_process_id != context.process.id:
            return TaskResult.fail(
                f"Process {process_id} is not a sub-workflow of process {context.process.id}"
            )

        if task.properties.get("timeout"):
            logger.warning(
                "wait_subworkflow ignores timeout: set it on the subworkflow that starts %s",
                process_id,
            )

        # The engine re-runs this action with subflow_results once the child is terminal.
        return TaskResult.suspend([process_id])
