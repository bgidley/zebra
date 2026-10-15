"""ExecuteGoalWorkflowAction - Execute a goal workflow by name."""

import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from zebra.core.models import ProcessInstance, ProcessState, TaskInstance, TaskResult, TaskState
from zebra.forms import resolve_task_schema
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.agent.followup import (
    CONTINUATION_DECISION_KEY,
    PREVIOUS_RUN_CONTEXT_KEY,
    with_previous_run,
)
from zebra_tasks.agent.history import with_workflow_history
from zebra_tasks.agent.user_context import copy_user_properties

if TYPE_CHECKING:
    from zebra_agent.library import WorkflowLibrary

logger = logging.getLogger(__name__)

# Task property recording the child process this task spawned (F129 re-attach).
CHILD_PROCESS_ID_KEY = "__child_process_id__"
# Child property recording the failed process a retry resumed from (#187).
RESUMED_FROM_KEY = "__resumed_from__"
_DONE_TASK_STATES = {TaskState.COMPLETE}


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
        continue_on_failure: When true, a failed/timed-out child completes this task
            with ``success: false`` in the output instead of failing it, so downstream
            tasks (e.g. assess_and_record) still run (default: false)

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
        ParameterDef(
            name="continue_on_failure",
            type="bool",
            description="Complete with success=false in the output instead of failing the task",
            required=False,
            default=False,
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
        """Start the goal workflow and suspend on it; collect its result on resume.

        The task suspends on the child (#185) instead of polling it, so a goal parked
        on the child's human task returns from ``start_process`` (no goal timeout
        runs while a human answers) and failing the goal fails the child.
        """
        output_key = task.properties.get("output_key", "execution_result")
        continue_on_failure = task.properties.get("continue_on_failure", False)
        if isinstance(continue_on_failure, str):
            continue_on_failure = continue_on_failure.lower() in ("true", "1", "yes")

        if context.subflow_results is not None:
            result = await self._collect_child(task, context)
            return self._finish(result, context, output_key, continue_on_failure)

        workflow_name = task.properties.get("workflow_name")
        goal = task.properties.get("goal")
        timeout = float(task.properties.get("timeout", 120))

        # Resolve templates if needed
        if isinstance(workflow_name, str) and "{{" in workflow_name:
            workflow_name = context.resolve_template(workflow_name)
        if isinstance(goal, str) and "{{" in goal:
            goal = context.resolve_template(goal)

        if not workflow_name:
            return TaskResult.fail("No workflow_name provided")
        if not goal:
            return TaskResult.fail("No goal provided")

        # Get workflow library - try IoC container, then context.extras (engine-level injection)
        library = self.workflow_library
        if library is None:
            library = context.extras.get("__workflow_library__")

        if library is None:
            return TaskResult.fail("No workflow library available")

        try:
            # Load workflow definition
            definition = library.get_workflow(workflow_name)
        except ValueError as e:
            return TaskResult.fail(f"Failed to load workflow: {e}")

        try:
            # Emit progress event: workflow starting
            callback = context.extras.get("__progress_callback__")
            if callback:
                await callback(
                    "workflow_starting",
                    {
                        "total_tasks": len(definition.tasks),
                        "workflow_name": workflow_name,
                    },
                )

            # F129: re-attach to a child spawned by an earlier, interrupted run of
            # this task instead of creating a duplicate — makes re-running safe.
            sub_process = await self._find_existing_child(task, context)
            if sub_process is not None:
                logger.info(
                    "ExecuteGoalWorkflowAction re-attaching to child %s (state=%s)",
                    sub_process.id,
                    sub_process.state.value,
                )
                if sub_process.state == ProcessState.CREATED:
                    resumed = sub_process.properties.get(RESUMED_FROM_KEY) or {}
                    await context.engine.start_process_with_timeout(
                        sub_process.id, timeout, start_task_ids=resumed.get("task_ids")
                    )
            else:
                sub_process = await self._spawn_child(task, context, definition, goal, timeout)
        except Exception as e:
            error_result = {
                "success": False,
                "output": None,
                "tokens_used": 0,
                "cost": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
                "error": str(e),
            }
            return self._finish(error_result, context, output_key, continue_on_failure)

        # The child has finished, failed, or parked on a human task. The engine
        # re-runs this action with subflow_results once it is terminal (#146).
        return TaskResult.suspend([sub_process.id])

    def _finish(
        self,
        result: dict[str, Any],
        context: ExecutionContext,
        output_key: str,
        continue_on_failure: bool,
    ) -> TaskResult:
        """Store *result* on the process and turn it into this task's result."""
        context.set_process_property(output_key, result)
        if result["success"] or continue_on_failure:
            return TaskResult.ok(output=result)
        logger.warning(f"ExecuteGoalWorkflowAction returning fail: {result.get('error')}")
        return TaskResult.fail(result.get("error", "Workflow execution failed"))

    async def _collect_child(self, task: TaskInstance, context: ExecutionContext) -> dict[str, Any]:
        """Build the execution result from the finished child this task waited on."""
        child_id = task.properties.get(CHILD_PROCESS_ID_KEY)
        child = await context.store.load_process(child_id) if child_id else None
        if child is None:
            return {
                "success": False,
                "output": None,
                "tokens_used": 0,
                "cost": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
                "error": "Process not found",
            }
        definition = await context.store.load_definition(child.definition_id)
        properties = child.properties
        token_history = properties.get("__token_history__", [])
        success = child.state == ProcessState.COMPLETE
        error = None
        if child.state == ProcessState.FAILED:
            error = str(properties.get("__error__", "Process failed"))
        elif not success:
            error = f"Child process is still {child.state.value}"

        self._record_task_executions(child, definition, error, context)
        callback = context.extras.get("__progress_callback__")
        if callback:
            await self._emit_task_progress(callback, child, definition)

        logger.info("ExecuteGoalWorkflowAction collected child %s: success=%s", child.id, success)
        return {
            "success": success,
            "output": self._extract_output(properties, definition) if success else None,
            "tokens_used": properties.get("__total_tokens__", 0),
            "cost": properties.get("__total_cost__", 0.0),
            "input_tokens": sum(e.get("input", 0) for e in token_history),
            "output_tokens": sum(e.get("output", 0) for e in token_history),
            "error": error,
            "user_inputs": self._extract_user_inputs(properties, definition),
        }

    @staticmethod
    def _completed_task_ids(child: ProcessInstance) -> list[str]:
        """Task definition ids of the child's completed tasks, in completion order."""
        prefix = "__task_output_"
        return [k[len(prefix) :] for k in child.properties if k.startswith(prefix)]

    def _record_task_executions(
        self,
        child: ProcessInstance,
        definition: Any,
        error: str | None,
        context: ExecutionContext,
    ) -> None:
        """Append the child's task executions to ``__task_executions__`` for metrics."""
        tasks = getattr(definition, "tasks", None) or {}
        now = datetime.now(UTC).isoformat()
        executions = []
        for order, task_id in enumerate(self._completed_task_ids(child), start=1):
            output = child.properties.get(f"__task_output_{task_id}")
            task_def = tasks.get(task_id)
            executions.append(
                {
                    "id": str(uuid.uuid4()),
                    "run_id": context.process.properties.get("run_id", child.id),
                    "task_definition_id": task_id,
                    "task_name": task_def.name if task_def else task_id,
                    "execution_order": order,
                    "state": "complete",
                    "started_at": now,
                    "completed_at": now,
                    "output": str(output)[:500] if output else None,
                    "error": None,
                }
            )
        if not executions:
            return
        if error:
            executions[-1]["state"] = "failed"
            executions[-1]["error"] = error
        current = context.process.properties.get("__task_executions__", [])
        context.set_process_property("__task_executions__", current + executions)

    async def _emit_task_progress(
        self, callback: Any, child: ProcessInstance, definition: Any
    ) -> None:
        """Emit ``task_completed`` progress events for the child's completed tasks."""
        tasks = getattr(definition, "tasks", None) or {}
        for index, task_id in enumerate(self._completed_task_ids(child), start=1):
            output = child.properties.get(f"__task_output_{task_id}")
            task_def = tasks.get(task_id)
            await callback(
                "task_completed",
                {
                    "task_name": task_def.name if task_def else task_id,
                    "task_index": index,
                    "total_tasks": len(tasks),
                    "output_preview": str(output)[:200] if output else None,
                },
            )

    async def _find_existing_child(
        self, task: TaskInstance, context: ExecutionContext
    ) -> ProcessInstance | None:
        """Return the child process an earlier run of this task spawned, if any.

        The child id is recorded on the task (``__child_process_id__``) before the
        child starts. It is only trusted while the child is still linked to this
        parent process and task (``parent_process_id`` / ``parent_task_id``).
        """
        child_id = task.properties.get(CHILD_PROCESS_ID_KEY)
        if not child_id:
            return None
        child = await context.store.load_process(child_id)
        if child is None:
            return None
        if child.parent_process_id != context.process.id or child.parent_task_id != task.id:
            logger.warning(
                "Recorded child %s is not linked to task %s; spawning a new child",
                child_id,
                task.id,
            )
            return None
        return child

    async def _spawn_child(
        self,
        task: TaskInstance,
        context: ExecutionContext,
        definition: Any,
        goal: str,
        timeout: float,
    ) -> ProcessInstance:
        """Create, link, record and start a new child process for this task.

        The child's inline auto-task chain is bounded by *timeout* (#142); on expiry
        the child is failed and ``_collect_child`` reports its error on resume.
        """
        # F116: a follow-up goal carries the previous run's context into the
        # executed workflow, which only sees the goal.
        sub_properties = {
            # F138: append any workflow history fetched earlier in the loop.
            "goal": with_workflow_history(
                with_previous_run(goal, context.process.properties), context.process.properties
            ),
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

        # The goal workflow runs as the submitting user (trust gate, knowledge; #151)
        copy_user_properties(context.process.properties, sub_properties)

        # #187: retrying a failed run resumes where it stopped, keeping the answers
        # already given, instead of asking every question again.
        start_task_ids = None
        resume = await self._resume_point(context, definition)
        if resume is not None:
            previous, start_task_ids = resume
            sub_properties = {**self._carried_properties(previous), **sub_properties}
            sub_properties[RESUMED_FROM_KEY] = {
                "process_id": previous.id,
                "task_ids": start_task_ids,
            }
            logger.info(
                "ExecuteGoalWorkflowAction resuming %s from failed process %s at %s",
                definition.name,
                previous.id,
                start_task_ids,
            )

        sub_process = await context.engine.create_process(definition, properties=sub_properties)

        # Link as child process
        sub_process.parent_process_id = context.process.id
        sub_process.parent_task_id = task.id
        await context.store.save_process(sub_process)

        # F129: record the child on the task *before* starting it, so a re-run
        # after an interruption re-attaches instead of spawning a duplicate.
        task.properties[CHILD_PROCESS_ID_KEY] = sub_process.id
        await context.store.save_task(task)

        await context.engine.start_process_with_timeout(
            sub_process.id, timeout, start_task_ids=start_task_ids
        )
        return sub_process

    async def _resume_point(
        self, context: ExecutionContext, definition: Any
    ) -> tuple[ProcessInstance, list[str]] | None:
        """Find where a retried run stopped, if this goal retries one (#187).

        Applies when the continuation assessor chose ``same_workflow`` for a
        previous run that failed in this same workflow. Returns that run's failed
        goal-workflow process and the ids of its tasks that never completed (the
        ones to start at), or None to start the workflow from the beginning.
        """
        props = context.process.properties
        previous_run = props.get(PREVIOUS_RUN_CONTEXT_KEY)
        if props.get(CONTINUATION_DECISION_KEY) != "same_workflow":
            return None
        if not isinstance(previous_run, dict) or previous_run.get("success", True):
            return None
        if previous_run.get("workflow_name") != definition.name or not previous_run.get("run_id"):
            return None
        try:
            child = await self._previous_child(context, previous_run["run_id"], definition.name)
            if child is None:
                return None
            tasks = await context.store.load_tasks_for_process(child.id)
        except Exception:
            logger.warning("Could not find where run %s stopped", previous_run, exc_info=True)
            return None
        start = []
        for t in tasks:
            if t.state in _DONE_TASK_STATES or t.task_definition_id in start:
                continue
            task_def = definition.tasks.get(t.task_definition_id)
            if task_def is None or task_def.synchronized:
                # The workflow changed since, or a join would wait on branches that
                # never run again: start from the beginning instead.
                logger.info("Not resuming %s at %s", child.id, t.task_definition_id)
                return None
            start.append(t.task_definition_id)
        return (child, start) if start else None

    @staticmethod
    async def _previous_child(
        context: ExecutionContext, run_id: str, workflow_name: str
    ) -> ProcessInstance | None:
        """The failed goal-workflow process of run *run_id*, newest first."""
        for state in (ProcessState.FAILED, ProcessState.COMPLETE):
            for root in await context.store.get_processes_by_state(state, exclude_children=True):
                if (root.properties or {}).get("run_id") != run_id:
                    continue
                for child in reversed(await context.store.list_child_processes(root.id)):
                    if child.state != ProcessState.FAILED:
                        continue
                    child_def = await context.store.load_definition(child.definition_id)
                    if child_def is not None and child_def.name == workflow_name:
                        return child
                return None
        return None

    @staticmethod
    def _carried_properties(previous: ProcessInstance) -> dict[str, Any]:
        """Workflow state to carry into the resumed process.

        The workflow's own properties and completed task outputs; engine
        bookkeeping (errors, cost and token totals, parent links) starts afresh.
        """
        return {
            k: v
            for k, v in previous.properties.items()
            if not k.startswith("__") or k.startswith("__task_output_")
        }

    @staticmethod
    def _extract_user_inputs(properties: dict[str, Any], definition: Any) -> dict[str, Any]:
        """Answers the user gave to the child's human (``auto: false``) tasks (F152).

        Keyed by task name; read-only form fields (values the workflow showed the
        user) are left out so only what the user typed remains.
        """
        inputs: dict[str, Any] = {}
        tasks = getattr(definition, "tasks", None) or {}
        for task_id, task_def in tasks.items():
            if getattr(task_def, "auto", True):
                continue
            answer = properties.get(f"__task_output_{task_id}")
            if answer in (None, "", {}):
                continue
            if isinstance(answer, dict):
                schema = resolve_task_schema(task_def.properties.get("schema"), properties)
                schema_props = (schema or {}).get("properties") or {}
                answer = {
                    k: v
                    for k, v in answer.items()
                    if not (schema_props.get(k) or {}).get("readOnly")
                }
            inputs[task_def.name or task_id] = answer
        return inputs

    def _extract_output(self, properties: dict[str, Any], definition: Any = None) -> Any:
        """Extract output from process properties.

        Uses `result_key` from definition.properties if set, otherwise falls
        back to scanning standard output keys, then all non-internal properties.
        """
        # Use result_key declared in the workflow definition
        if definition is not None:
            result_key = getattr(definition, "properties", {}).get("result_key")
            if result_key and result_key in properties:
                return properties[result_key]

        # Try standard output keys
        for key in self.OUTPUT_KEYS:
            if key in properties:
                return properties[key]

        # Fall back to all non-internal properties
        return {k: v for k, v in properties.items() if not k.startswith("__")}
