"""RecordMetricsAction - Record workflow run and task executions to metrics store."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

if TYPE_CHECKING:
    from zebra_agent.storage.interfaces import MetricsStore


class RecordMetricsAction(TaskAction):
    """
    Record workflow run and task executions to the metrics store.

    This action creates a WorkflowRun record and optionally records
    associated TaskExecution records.

    Properties:
        run_id: Unique identifier for the run
        workflow_name: Name of the workflow that was executed
        goal: The user's original goal
        success: Whether the workflow completed successfully
        output: The workflow output (optional)
        tokens_used: Number of tokens used (optional)
        error: Error message if failed (optional)
        task_executions: List of task execution records (optional)

    Example workflow usage:
        ```yaml
        tasks:
          record_metrics:
            name: "Record Metrics"
            action: record_metrics
            auto: true
            properties:
              run_id: "{{run_id}}"
              workflow_name: "{{workflow_name}}"
              goal: "{{goal}}"
              success: "{{execution_result.success}}"
              output: "{{execution_result.output}}"
              tokens_used: "{{execution_result.tokens_used}}"
        ```
    """

    description = "Record workflow run and task executions to metrics store."

    inputs = [
        ParameterDef(
            name="run_id",
            type="string",
            description="Unique identifier for the run",
            required=True,
        ),
        ParameterDef(
            name="workflow_name",
            type="string",
            description="Name of the workflow that was executed",
            required=True,
        ),
        ParameterDef(
            name="goal",
            type="string",
            description="The user's original goal",
            required=True,
        ),
        ParameterDef(
            name="success",
            type="bool",
            description="Whether the workflow completed successfully",
            required=True,
        ),
        ParameterDef(
            name="output",
            type="any",
            description="The workflow output",
            required=False,
        ),
        ParameterDef(
            name="tokens_used",
            type="int",
            description="Number of tokens used",
            required=False,
            default=0,
        ),
        ParameterDef(
            name="error",
            type="string",
            description="Error message if failed",
            required=False,
        ),
        ParameterDef(
            name="started_at",
            type="string",
            description="ISO format timestamp when the run started",
            required=False,
        ),
    ]

    outputs = [
        ParameterDef(
            name="recorded",
            type="bool",
            description="Whether the metrics were recorded successfully",
            required=True,
        ),
    ]

    def __init__(self, metrics_store: "MetricsStore | None" = None):
        """
        Initialize the action.

        Args:
            metrics_store: Metrics store for recording runs.
                          If None, will try to get from IoC container at runtime.
        """
        self.metrics_store = metrics_store

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Record workflow run metrics."""
        # Import here to avoid circular imports
        from zebra_agent.metrics import WorkflowRun

        # Get metrics store - try IoC container, then context.extras (engine-level injection)
        metrics_store = self.metrics_store
        if metrics_store is None:
            metrics_store = context.extras.get("__metrics_store__")

        if metrics_store is None:
            # No metrics store available - skip recording but don't fail
            return TaskResult.ok(output={"recorded": False})

        try:
            # Extract run data from properties
            run_id = task.properties.get("run_id")
            workflow_name = task.properties.get("workflow_name")
            goal = task.properties.get("goal")
            started_at_str = task.properties.get("started_at")

            # Resolve templates if needed
            if isinstance(run_id, str) and "{{" in run_id:
                run_id = context.resolve_template(run_id)
            if isinstance(workflow_name, str) and "{{" in workflow_name:
                workflow_name = context.resolve_template(workflow_name)
            if isinstance(goal, str) and "{{" in goal:
                goal = context.resolve_template(goal)

            # Extract success/output/tokens_used/error.
            # First try reading from the execution_result process property (set by
            # execute_goal_workflow action), since YAML templates like
            # {{execution_result.success}} don't support nested dict access.
            # Fall back to task properties for direct (non-template) usage.
            execution_result = context.get_process_property("execution_result")
            if isinstance(execution_result, dict) and "success" in execution_result:
                success = execution_result.get("success", False)
                output = execution_result.get("output")
                tokens_used = execution_result.get("tokens_used", 0)
                error = execution_result.get("error")
            else:
                success = task.properties.get("success", False)
                output = task.properties.get("output")
                tokens_used = task.properties.get("tokens_used", 0)
                error = task.properties.get("error")

            # Parse started_at if provided
            if started_at_str:
                started_at = datetime.fromisoformat(started_at_str)
            else:
                # Use process property if available, otherwise now
                started_at = context.process.properties.get(
                    "__started_at__", datetime.now(timezone.utc)
                )
                if isinstance(started_at, str):
                    started_at = datetime.fromisoformat(started_at)

            # Create WorkflowRun record
            run = WorkflowRun(
                id=run_id,
                workflow_name=workflow_name,
                goal=goal,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                success=bool(success),
                tokens_used=tokens_used or 0,
                error=error,
                output=self._serialize_output(output),
            )

            # Record the run
            await metrics_store.record_run(run)

            # Record task executions if available
            task_executions = context.process.properties.get("__task_executions__", [])
            if task_executions:
                await metrics_store.record_task_executions(task_executions)

            return TaskResult.ok(output={"recorded": True})

        except Exception as e:
            # Don't fail the workflow just because metrics recording failed
            return TaskResult.ok(
                output={
                    "recorded": False,
                    "error": str(e),
                }
            )

    def _serialize_output(self, output: Any) -> Any:
        """Ensure output is JSON-serializable."""
        if output is None:
            return None

        # Try to convert to a JSON-safe format
        if isinstance(output, (str, int, float, bool)):
            return output
        elif isinstance(output, dict):
            return {k: self._serialize_output(v) for k, v in output.items()}
        elif isinstance(output, (list, tuple)):
            return [self._serialize_output(v) for v in output]
        else:
            # Convert to string as fallback
            return str(output)
