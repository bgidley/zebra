"""QueueGoalAction — create a CREATED process for later budget-managed execution.

This action is the second step of the "Create Goal" workflow.  It receives
goal text, priority, and optional deadline from the human-input step, then
creates a new "Agent Main Loop" process in ``CREATED`` state (without starting
it).  The budget daemon picks these processes up and starts them when budget
allows.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

logger = logging.getLogger(__name__)


class QueueGoalAction(TaskAction):
    """Queue a goal for budget-managed execution.

    Creates an "Agent Main Loop" process in ``CREATED`` state with the
    supplied goal, priority, and deadline in its properties.

    Properties:
        goal: The user's goal text
        priority: Priority 1-5 (default 3)
        deadline: Optional ISO datetime deadline
        output_key: Where to store the result (default "queue_result")

    Output:
        - queued: bool
        - process_id: str — ID of the created process
    """

    description = "Queue a goal for later budget-managed execution."

    inputs = [
        ParameterDef(name="goal", type="string", description="Goal text", required=True),
        ParameterDef(
            name="priority", type="int", description="Priority 1-5", required=False, default=3
        ),
        ParameterDef(
            name="deadline",
            type="string",
            description="Optional ISO datetime deadline",
            required=False,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key for the result",
            required=False,
            default="queue_result",
        ),
    ]

    outputs = [
        ParameterDef(name="queued", type="bool", description="Whether goal was queued"),
        ParameterDef(name="process_id", type="string", description="ID of the created process"),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Create a CREATED process for the Agent Main Loop workflow."""
        # Resolve templates
        goal = self._resolve(task, context, "goal", "")
        priority = self._resolve(task, context, "priority", "3")
        deadline = self._resolve(task, context, "deadline", "")
        output_key = task.properties.get("output_key", "queue_result")

        if not goal:
            return TaskResult.fail("No goal provided")

        # Normalise priority
        try:
            priority = int(priority)
        except (TypeError, ValueError):
            priority = 3
        priority = max(1, min(5, priority))

        # Get the workflow library to load the Agent Main Loop definition
        library = context.extras.get("__workflow_library__")
        if library is None:
            return TaskResult.fail("No workflow library available")

        try:
            definition = library.get_workflow("Agent Main Loop")
        except ValueError as e:
            return TaskResult.fail(f"Cannot load Agent Main Loop workflow: {e}")

        # Gather available workflows (same as AgentLoop.process_goal does)
        workflows = await library.list_workflows()
        available = [
            {
                "name": w.name,
                "description": w.description,
                "tags": w.tags,
                "success_rate": f"{w.success_rate:.0%}" if w.use_count > 0 else "N/A",
                "use_count": w.use_count,
                "use_when": w.use_when,
            }
            for w in workflows
            if "system" not in (w.tags or [])
        ]

        # Build process properties
        run_id = str(uuid.uuid4())
        properties: dict = {
            "goal": goal,
            "run_id": run_id,
            "priority": priority,
            "available_workflows": available,
            "__started_at__": datetime.now(UTC).isoformat(),
        }
        if deadline:
            properties["deadline"] = deadline

        # Copy LLM settings from the parent process
        if "__llm_provider_name__" in context.process.properties:
            properties["__llm_provider_name__"] = context.process.properties[
                "__llm_provider_name__"
            ]
        if "__llm_model__" in context.process.properties:
            properties["__llm_model__"] = context.process.properties["__llm_model__"]

        try:
            # Create the process in CREATED state — do NOT start it
            process = await context.engine.create_process(definition, properties=properties)
            logger.info(
                "QueueGoalAction: queued goal as process %s (priority=%d, deadline=%s)",
                process.id[:12],
                priority,
                deadline or "none",
            )

            result = {
                "queued": True,
                "process_id": process.id,
                "run_id": run_id,
                "priority": priority,
                "deadline": deadline or None,
            }
            context.set_process_property(output_key, result)
            return TaskResult.ok(output=result)

        except Exception as e:
            logger.exception("QueueGoalAction: failed to create process")
            return TaskResult.fail(f"Failed to queue goal: {e}")

    def _resolve(
        self, task: TaskInstance, context: ExecutionContext, key: str, default: str
    ) -> str:
        """Resolve a string property, expanding templates."""
        value = task.properties.get(key, default)
        if isinstance(value, str) and "{{" in value:
            value = context.resolve_template(value)
        return value or default
