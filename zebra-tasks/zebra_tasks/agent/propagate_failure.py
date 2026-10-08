"""PropagateFailureAction - re-raise a recorded failure at the end of a workflow.

Pairs with ``execute_goal_workflow``'s ``continue_on_failure`` option (GitLab #140):
the goal run's failure is carried as data through the learning steps
(assess_and_record, update_conceptual_memory) and then turned back into a task
failure here, so the process still ends FAILED with the original error.
"""

import logging

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

logger = logging.getLogger(__name__)


class PropagateFailureAction(TaskAction):
    """Fail with ``error`` when ``success`` is false; succeed otherwise.

    Example workflow usage:
        ```yaml
        report_outcome:
          name: "Report Outcome"
          action: propagate_failure
          properties:
            success: "{{execution_result.success}}"
            error: "{{execution_result.error}}"
        ```
    """

    description = "Fail the task with the given error when success is false; otherwise succeed."
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(
            name="success",
            type="bool",
            description="Outcome to propagate",
            required=True,
        ),
        ParameterDef(
            name="error",
            type="string",
            description="Error to fail with when success is false",
            required=False,
            default="",
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Propagate the outcome as the task result."""
        success = task.properties.get("success", False)
        if isinstance(success, str):
            if "{{" in success:
                success = context.resolve_template(success)
            success = success.lower() in ("true", "1", "yes")

        if success:
            return TaskResult.ok()

        error = task.properties.get("error") or ""
        if isinstance(error, str) and "{{" in error:
            error = context.resolve_template(error)
        error = error or "Workflow execution failed"
        logger.info("PropagateFailureAction failing with: %s", error)
        return TaskResult.fail(error)
