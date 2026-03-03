"""ConsultMemoryAction - consult conceptual memory to produce a workflow shortlist."""

import logging

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

logger = logging.getLogger(__name__)


class ConsultMemoryAction(TaskAction):
    """
    Consult conceptual memory to get a shortlist of recommended workflows for a goal.

    This is the first step of the new agent loop. It reads the conceptual memory
    index (goal-pattern → workflow mapping) and returns a shortlist of candidates
    plus raw memory context for the downstream selector.

    If no memory store is available or memory is empty, it gracefully returns an
    empty shortlist so the selector falls back to the full workflow list.

    Properties:
        goal: The user's goal/request
        output_key: Where to store the shortlist (default: "memory_shortlist")

    Output:
        - shortlist: list of workflow names recommended by memory
        - memory_context: formatted LLM-ready string of conceptual memory
        - has_memory: bool indicating whether memory context exists

    Routes:
        No route — always continues to next task.

    Example workflow usage:
        ```yaml
        tasks:
          consult_memory:
            name: "Consult Memory"
            action: consult_memory
            auto: true
            properties:
              goal: "{{goal}}"
              output_key: memory_shortlist
        ```
    """

    description = "Consult conceptual memory for workflow shortlist before selection."

    inputs = [
        ParameterDef(
            name="goal",
            type="string",
            description="The user's goal/request",
            required=True,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the shortlist result",
            required=False,
            default="memory_shortlist",
        ),
    ]

    outputs = [
        ParameterDef(
            name="shortlist",
            type="list",
            description="Workflow names recommended by conceptual memory",
            required=True,
        ),
        ParameterDef(
            name="memory_context",
            type="string",
            description="Formatted conceptual memory context for LLM injection",
            required=True,
        ),
        ParameterDef(
            name="has_memory",
            type="bool",
            description="Whether memory context exists",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Consult conceptual memory and produce a shortlist."""
        goal = task.properties.get("goal", "")
        if isinstance(goal, str) and "{{" in goal:
            goal = context.resolve_template(goal)

        output_key = task.properties.get("output_key", "memory_shortlist")

        # Get memory store from engine extras (graceful degradation)
        memory_store = context.extras.get("__memory_store__")
        if memory_store is None:
            logger.info("No memory store available — returning empty shortlist")
            result = {"shortlist": [], "memory_context": "", "has_memory": False}
            context.set_process_property(output_key, result)
            return TaskResult.ok(output=result)

        try:
            # Get conceptual memory context (compact summary for LLM)
            memory_context = await memory_store.get_conceptual_context_for_llm()

            # Extract shortlist: all workflows mentioned in conceptual memory
            # that appear relevant to the goal. We pass the full list to the
            # selector; the selector uses the context string for ranking.
            conceptual_entries = await memory_store.get_conceptual_memories(limit=50)
            shortlist: list[str] = []
            for entry in conceptual_entries:
                for wf in entry.recommended_workflows:
                    name = wf.get("name")
                    if name and name not in shortlist:
                        shortlist.append(name)

            has_memory = bool(memory_context)

            logger.info(
                f"ConsultMemoryAction: {len(conceptual_entries)} concepts, "
                f"{len(shortlist)} shortlisted workflows"
            )

            result = {
                "shortlist": shortlist,
                "memory_context": memory_context,
                "has_memory": has_memory,
            }
            context.set_process_property(output_key, result)
            return TaskResult.ok(output=result)

        except Exception as e:
            logger.warning(f"ConsultMemoryAction failed — degrading gracefully: {e}")
            result = {"shortlist": [], "memory_context": "", "has_memory": False}
            context.set_process_property(output_key, result)
            return TaskResult.ok(output=result)
