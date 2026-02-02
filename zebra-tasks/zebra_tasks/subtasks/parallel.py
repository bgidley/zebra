"""ParallelSubworkflowsAction - Spawn and wait for multiple sub-workflows in parallel."""

from typing import Any

from zebra.core.models import ProcessDefinition, TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction
from zebra.definitions.loader import load_definition_from_yaml


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
        timeout: Timeout in seconds for all workflows (optional)
        fail_fast: Stop all on first failure (default: False)
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
            description="Timeout in seconds for all workflows",
            required=False,
        ),
        ParameterDef(
            name="fail_fast",
            type="bool",
            description="Stop all workflows on first failure",
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
        """Execute multiple sub-workflows in parallel."""
        import asyncio

        workflows = task.properties.get("workflows", [])
        if not workflows:
            return TaskResult.fail("No workflows specified")

        timeout = task.properties.get("timeout")
        fail_fast = task.properties.get("fail_fast", False)

        # Spawn all workflows
        spawned: list[tuple[str, str]] = []  # (key, process_id)
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

            # Create and start sub-process
            sub_process = await context.engine.create_process(
                workflow_def,
                properties=resolved_properties,
            )
            sub_process.parent_process_id = context.process.id
            sub_process.parent_task_id = task.id
            await context.store.save_process(sub_process)
            await context.engine.start_process(sub_process.id)

            spawned.append((key, sub_process.id))

        # Wait for all to complete
        results: dict[str, Any] = {}
        all_success = True

        async def wait_for_one(key: str, process_id: str) -> tuple[str, dict]:
            result = await self._wait_for_completion(context, process_id, timeout)
            return key, result

        # Create tasks for waiting
        wait_tasks = [asyncio.create_task(wait_for_one(key, pid)) for key, pid in spawned]

        # Gather results
        if fail_fast:
            # Stop on first failure
            for coro in asyncio.as_completed(wait_tasks):
                key, result = await coro
                results[key] = result
                if not result.get("success", False):
                    all_success = False
                    # Cancel remaining tasks
                    for t in wait_tasks:
                        if not t.done():
                            t.cancel()
                    break
        else:
            # Wait for all
            completed = await asyncio.gather(*wait_tasks, return_exceptions=True)
            for item in completed:
                if isinstance(item, Exception):
                    all_success = False
                else:
                    key, result = item
                    results[key] = result
                    if not result.get("success", False):
                        all_success = False

        # Store results
        output_key = task.properties.get("output_key", "parallel_results")
        context.set_process_property(output_key, results)

        if all_success:
            return TaskResult.ok(output=results)
        else:
            return TaskResult(
                success=True, output=results, next_route="partial_failure" if results else "failure"
            )

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
            if timeout:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout:
                    return {
                        "success": False,
                        "error": f"Timeout after {timeout}s",
                        "process_id": process_id,
                    }

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

            await asyncio.sleep(0.1)
