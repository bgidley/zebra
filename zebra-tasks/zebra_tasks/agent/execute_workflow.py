"""ExecuteGoalWorkflowAction - Execute a goal workflow by name."""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from zebra.core.models import ProcessState, TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

if TYPE_CHECKING:
    from zebra_agent.library import WorkflowLibrary
    from zebra_agent.metrics import TaskExecution


class ExecuteGoalWorkflowAction(TaskAction):
    """
    Execute a goal workflow by name and capture its output.

    This action loads a workflow definition from the library, creates
    a subprocess, executes it with the given goal, and returns the result.

    Properties:
        workflow_name: Name of the workflow to execute
        goal: The user's goal to pass to the workflow
        timeout: Maximum execution time in seconds (default: 120)
        output_key: Where to store the execution result (default: "execution_result")

    Output:
        - success: bool - Whether the workflow completed successfully
        - output: any - The workflow's output
        - tokens_used: int - Total tokens used
        - error: str | None - Error message if failed

    Example workflow usage:
        ```yaml
        tasks:
          execute_workflow:
            name: "Execute Goal Workflow"
            action: execute_goal_workflow
            auto: true
            properties:
              workflow_name: "{{workflow_name}}"
              goal: "{{goal}}"
              timeout: 120
              output_key: execution_result
        ```
    """

    description = "Execute a goal workflow by name and capture its output."

    inputs = [
        ParameterDef(
            name="workflow_name",
            type="string",
            description="Name of the workflow to execute",
            required=True,
        ),
        ParameterDef(
            name="goal",
            type="string",
            description="The user's goal to pass to the workflow",
            required=True,
        ),
        ParameterDef(
            name="timeout",
            type="float",
            description="Maximum execution time in seconds",
            required=False,
            default=120,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the result",
            required=False,
            default="execution_result",
        ),
    ]

    outputs = [
        ParameterDef(
            name="success",
            type="bool",
            description="Whether the workflow completed successfully",
            required=True,
        ),
        ParameterDef(
            name="output",
            type="any",
            description="The workflow's output",
            required=False,
        ),
        ParameterDef(
            name="tokens_used",
            type="int",
            description="Total tokens used during execution",
            required=True,
        ),
        ParameterDef(
            name="error",
            type="string",
            description="Error message if workflow failed",
            required=False,
        ),
    ]

    # Standard output keys to look for in workflow results
    OUTPUT_KEYS = [
        "answer",
        "summary",
        "ideas",
        "refined_ideas",
        "solutions",
        "result",
        "output",
        "complete_guide",
        "techniques",
        "response",
    ]

    def __init__(self, workflow_library: "WorkflowLibrary | None" = None):
        """
        Initialize the action.

        Args:
            workflow_library: Library for loading workflow definitions.
                             If None, will try to get from IoC container at runtime.
        """
        self.workflow_library = workflow_library

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Execute the goal workflow."""
        workflow_name = task.properties.get("workflow_name")
        goal = task.properties.get("goal")
        timeout = task.properties.get("timeout", 120)
        output_key = task.properties.get("output_key", "execution_result")

        # Resolve templates if needed
        if isinstance(workflow_name, str) and "{{" in workflow_name:
            workflow_name = context.resolve_template(workflow_name)
        if isinstance(goal, str) and "{{" in goal:
            goal = context.resolve_template(goal)

        if not workflow_name:
            return TaskResult.fail("No workflow_name provided")
        if not goal:
            return TaskResult.fail("No goal provided")

        # Get workflow library - try IoC container if not injected
        library = self.workflow_library
        if library is None:
            library = context.process.properties.get("__workflow_library__")

        if library is None:
            return TaskResult.fail("No workflow library available")

        try:
            # Load workflow definition
            definition = library.get_workflow(workflow_name)
        except ValueError as e:
            return TaskResult.fail(f"Failed to load workflow: {e}")

        try:
            # Prepare properties for the sub-workflow
            sub_properties = {
                "goal": goal,
                "__parent_process_id__": context.process.id,
                "__parent_task_id__": task.id,
            }

            # Copy LLM provider settings from parent
            if "__llm_provider_name__" in context.process.properties:
                sub_properties["__llm_provider_name__"] = context.process.properties[
                    "__llm_provider_name__"
                ]
            if "__llm_model__" in context.process.properties:
                sub_properties["__llm_model__"] = context.process.properties["__llm_model__"]

            # Create sub-process
            sub_process = await context.engine.create_process(
                definition,
                properties=sub_properties,
            )

            # Link as child process
            sub_process.parent_process_id = context.process.id
            sub_process.parent_task_id = task.id
            await context.store.save_process(sub_process)

            # Start sub-process
            await context.engine.start_process(sub_process.id)

            # Wait for completion with task tracking
            result, task_executions = await self._wait_for_completion(
                context, sub_process.id, definition, timeout
            )

            # Store task executions for metrics recording
            if task_executions:
                current_execs = context.process.properties.get("__task_executions__", [])
                current_execs.extend(task_executions)
                context.set_process_property("__task_executions__", current_execs)

            # Store result
            context.set_process_property(output_key, result)

            if result["success"]:
                return TaskResult.ok(output=result)
            else:
                return TaskResult.fail(result.get("error", "Workflow execution failed"))

        except Exception as e:
            error_result = {
                "success": False,
                "output": None,
                "tokens_used": 0,
                "error": str(e),
            }
            context.set_process_property(output_key, error_result)
            return TaskResult.fail(f"Workflow execution failed: {e}")

    async def _wait_for_completion(
        self,
        context: ExecutionContext,
        process_id: str,
        definition: Any,
        timeout: float,
    ) -> tuple[dict[str, Any], list["TaskExecution"]]:
        """Wait for sub-process to complete and extract results."""
        from zebra_agent.metrics import TaskExecution

        start_time = asyncio.get_event_loop().time()
        task_executions: list[TaskExecution] = []
        processed_tasks: set[str] = set()
        execution_order = 0
        total_tasks = len(definition.tasks)

        while True:
            # Check timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                return {
                    "success": False,
                    "output": None,
                    "tokens_used": 0,
                    "error": f"Timeout after {timeout}s",
                }, task_executions

            # Get process status
            process = await context.store.get_process(process_id)
            if process is None:
                return {
                    "success": False,
                    "output": None,
                    "tokens_used": 0,
                    "error": "Process not found",
                }, task_executions

            # Track task completions
            for key in process.properties:
                if key.startswith("__task_output_"):
                    task_id = key.replace("__task_output_", "")

                    if task_id in processed_tasks:
                        continue

                    processed_tasks.add(task_id)
                    execution_order += 1

                    # Get task definition
                    task_def = definition.tasks.get(task_id)
                    task_name = task_def.name if task_def else task_id

                    # Create task execution record
                    task_exec = TaskExecution(
                        id=str(uuid.uuid4()),
                        run_id=context.process.properties.get("run_id", process_id),
                        task_definition_id=task_id,
                        task_name=task_name,
                        execution_order=execution_order,
                        state="complete",
                        started_at=datetime.now(timezone.utc),
                        completed_at=datetime.now(timezone.utc),
                        output=process.properties.get(key),
                    )
                    task_executions.append(task_exec)

            # Check completion
            if process.state == ProcessState.COMPLETE:
                output = self._extract_output(process.properties)
                tokens = process.properties.get("__total_tokens__", 0)

                return {
                    "success": True,
                    "output": output,
                    "tokens_used": tokens,
                    "error": None,
                }, task_executions

            if process.state == ProcessState.FAILED:
                error = process.properties.get("__error__", "Process failed")

                # Mark last task as failed
                if task_executions:
                    task_executions[-1].state = "failed"
                    task_executions[-1].error = str(error)

                return {
                    "success": False,
                    "output": None,
                    "tokens_used": process.properties.get("__total_tokens__", 0),
                    "error": str(error),
                }, task_executions

            # Wait before checking again
            await asyncio.sleep(0.1)

    def _extract_output(self, properties: dict[str, Any]) -> Any:
        """Extract output from process properties using standard keys."""
        # Try standard output keys
        for key in self.OUTPUT_KEYS:
            if key in properties:
                return properties[key]

        # Fall back to all non-internal properties
        return {k: v for k, v in properties.items() if not k.startswith("__")}
