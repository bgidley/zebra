"""ParallelSubworkflowsAction - Spawn and wait for multiple sub-workflows in parallel."""

from typing import Any

from zebra.core.models import ProcessDefinition, ProcessState, TaskInstance, TaskResult
from zebra.definitions.loader import load_definition_from_yaml
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.subtasks.common import child_result, start_child

#: Task property mapping each child process id to its workflow key (#181).
SUBFLOW_KEYS_KEY = "__subflow_keys__"


class ParallelSubworkflowsAction(TaskAction):
    """
    TaskAction that spawns multiple sub-workflows in parallel and waits for all.

    This is useful when you need to run multiple independent operations
    concurrently and collect all results.

    Properties:
        workflows: List of workflow configs, each with:
            - workflow: Inline definition, YAML, or ID
            - workflow_file: Path to YAML file
            - properties: Properties to pass
            - key: Key to identify this result
        timeout: Seconds each child's inline auto-task run may take (optional)
        fail_fast: Start no more workflows once one fails (default: False)
        output_key: Where to store results dict in process properties

    Example workflow usage:
        ```yaml
        tasks:
          parallel_analysis:
            name: "Run Parallel Analysis"
            action: parallel_subworkflows
            properties:
              workflows:
                - workflow_file: "analysis/sentiment.yaml"
                  properties:
                    text: "{{input_text}}"
                  key: sentiment
                - workflow_file: "analysis/entities.yaml"
                  properties:
                    text: "{{input_text}}"
                  key: entities
                - workflow_file: "analysis/summary.yaml"
                  properties:
                    text: "{{input_text}}"
                  key: summary
              output_key: analysis_results
        ```
    """

    description = "Spawn multiple sub-workflows in parallel and wait for all to complete."

    inputs = [
        ParameterDef(
            name="workflows",
            type="list[dict]",
            description="List of workflow configs with workflow/workflow_file, properties, and key",
            required=True,
        ),
        ParameterDef(
            name="timeout",
            type="float",
            description="Seconds each child's inline auto-task run may take before it fails",
            required=False,
        ),
        ParameterDef(
            name="fail_fast",
            type="bool",
            description="Start no more workflows once one has failed",
            required=False,
            default=False,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the results dict",
            required=False,
            default="parallel_results",
        ),
    ]

    outputs = [
        ParameterDef(
            name="<workflow_key>",
            type="dict",
            description="Result for each workflow, keyed by the 'key' from workflow config",
            required=True,
        ),
        ParameterDef(
            name="<workflow_key>.success",
            type="bool",
            description="Whether the individual workflow completed successfully",
            required=True,
        ),
        ParameterDef(
            name="<workflow_key>.process_id",
            type="string",
            description="ID of the spawned sub-process",
            required=True,
        ),
        ParameterDef(
            name="<workflow_key>.properties",
            type="dict",
            description="Final properties of the sub-workflow",
            required=False,
        ),
        ParameterDef(
            name="<workflow_key>.output",
            type="any",
            description="Output from the sub-workflow's __output__ property",
            required=False,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Start the sub-workflows, suspend on them, and collect their results on resume.

        The task suspends on its children (#181) instead of polling them. Each child's
        key is kept on the task (``__subflow_keys__``) for the resume.
        """
        if context.subflow_results is not None:
            keys = task.properties.get(SUBFLOW_KEYS_KEY, {})
            results = {
                keys.get(entry["process_id"], entry["process_id"]): child_result(entry)
                for entry in context.subflow_results
            }
            return self._finish(task, context, results)

        workflows = task.properties.get("workflows", [])
        if not workflows:
            return TaskResult.fail("No workflows specified")

        timeout = task.properties.get("timeout")
        fail_fast = task.properties.get("fail_fast", False)

        # Spawn the workflows; with fail_fast, stop once one has failed
        keys: dict[str, str] = {}  # process_id -> key
        for i, wf_config in enumerate(workflows):
            key = wf_config.get("key", f"workflow_{i}")
            workflow_def = await self._get_workflow_definition(wf_config, context)

            if workflow_def is None:
                if fail_fast:
                    return TaskResult.fail(f"No workflow definition for {key}")
                continue

            # Resolve properties
            sub_properties = wf_config.get("properties", {})
            resolved_properties = {}
            for prop_key, value in sub_properties.items():
                if isinstance(value, str):
                    resolved_properties[prop_key] = context.resolve_template(value)
                else:
                    resolved_properties[prop_key] = value

            # Inherit parent context
            resolved_properties["__parent_process_id__"] = context.process.id
            resolved_properties["__parent_task_id__"] = task.id

            # Copy special properties
            for prop_key in context.process.properties:
                if prop_key.startswith("__") and prop_key not in resolved_properties:
                    resolved_properties[prop_key] = context.process.properties[prop_key]

            # Create and start sub-process; its inline run is bounded by timeout
            sub_process = await context.engine.create_process(
                workflow_def,
                properties=resolved_properties,
            )
            sub_process.parent_process_id = context.process.id
            sub_process.parent_task_id = task.id
            await context.store.save_process(sub_process)
            keys[sub_process.id] = key
            await start_child(context, sub_process.id, timeout)

            if fail_fast:
                started = await context.store.load_process(sub_process.id)
                if started is not None and started.state == ProcessState.FAILED:
                    break

        if not keys:
            return self._finish(task, context, {})

        # The engine re-runs this action with subflow_results once all are terminal.
        task.properties[SUBFLOW_KEYS_KEY] = keys
        return TaskResult.suspend(list(keys))

    def _finish(
        self, task: TaskInstance, context: ExecutionContext, results: dict[str, Any]
    ) -> TaskResult:
        """Store *results* and route on whether every sub-workflow succeeded."""
        output_key = task.properties.get("output_key", "parallel_results")
        context.set_process_property(output_key, results)

        if all(result["success"] for result in results.values()):
            return TaskResult.ok(output=results)
        return TaskResult(success=True, output=results, next_route="partial_failure")

    async def _get_workflow_definition(
        self, config: dict, context: ExecutionContext
    ) -> ProcessDefinition | None:
        """Get workflow definition from config."""
        workflow = config.get("workflow")
        if workflow:
            if isinstance(workflow, dict):
                return ProcessDefinition(**workflow)
            elif isinstance(workflow, str):
                if workflow.strip().startswith("name:"):
                    return load_definition_from_yaml(workflow)
                else:
                    return await context.store.get_definition(workflow)
            elif isinstance(workflow, ProcessDefinition):
                return workflow

        workflow_file = config.get("workflow_file")
        if workflow_file:
            resolved_path = context.resolve_template(workflow_file)
            with open(resolved_path) as f:
                return load_definition_from_yaml(f.read())

        return None
