"""ConsultMemoryAction - consult conceptual memory to produce a workflow shortlist."""

import logging

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction
from zebra_agent.storage.interfaces import (
    format_conceptual_context,
    format_lessons_context,
    format_similar_runs_context,
)

logger = logging.getLogger(__name__)

# How many goal-relevant concepts / similar past runs to give the selector (#169).
CONCEPT_LIMIT = 10
SIMILAR_RUNS_LIMIT = 5
# How many lessons from past incidents to recall (#175).
LESSONS_LIMIT = 3


class ConsultMemoryAction(TaskAction):
    """
    Consult conceptual memory to get a shortlist of recommended workflows for a goal.

    This is the first step of the new agent loop. It retrieves the conceptual
    memory entries (goal-pattern → workflow mapping) and past runs most relevant
    to the goal — by in-database vector similarity on Oracle, keyword overlap
    elsewhere (#169) — and returns a shortlist of candidates plus memory context
    for the downstream selector.

    If no memory store is available or memory is empty, it gracefully returns an
    empty shortlist so the selector falls back to the full workflow list.

    Properties:
        goal: The user's goal/request
        output_key: Where to store the shortlist (default: "memory_shortlist")

    Output:
        - shortlist: list of workflow names recommended by memory
        - memory_context: formatted LLM-ready string of conceptual memory
        - has_memory: bool indicating whether memory context exists
        - lessons_context: lessons from past incidents relevant to the goal (#175);
          also part of memory_context, and appended to the executed goal

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
            result = _empty_result()
            context.set_process_property(output_key, result)
            return TaskResult.ok(output=result)

        try:
            # Goal-relevant retrieval (#169): the concepts and past runs nearest
            # to this goal (vector search on Oracle, keyword ranking otherwise).
            conceptual_entries = await memory_store.search_conceptual_memories(
                goal, limit=CONCEPT_LIMIT
            )
            similar_runs = await memory_store.search_workflow_memories(
                goal, limit=SIMILAR_RUNS_LIMIT
            )

            # Shortlist: workflows recommended by the relevant concepts, then
            # workflows that succeeded on similar past goals.
            shortlist: list[str] = []
            for entry in conceptual_entries:
                for wf in entry.recommended_workflows:
                    name = wf.get("name")
                    if name and name not in shortlist:
                        shortlist.append(name)
            for run in similar_runs:
                if run.success and run.workflow_name not in shortlist:
                    shortlist.append(run.workflow_name)

            lessons_context = await _lessons_context(memory_store, goal)

            sections = [
                format_conceptual_context(conceptual_entries),
                format_similar_runs_context(similar_runs),
                lessons_context,
            ]
            memory_context = "\n\n".join(s for s in sections if s)
            has_memory = bool(memory_context)

            logger.info(
                f"ConsultMemoryAction: {len(conceptual_entries)} concepts, "
                f"{len(similar_runs)} similar runs, {len(shortlist)} shortlisted workflows"
            )

            result = {
                "shortlist": shortlist,
                "memory_context": memory_context,
                "has_memory": has_memory,
                "lessons_context": lessons_context,
            }
            context.set_process_property(output_key, result)
            return TaskResult.ok(output=result)

        except Exception as e:
            logger.warning(f"ConsultMemoryAction failed — degrading gracefully: {e}")
            result = _empty_result()
            context.set_process_property(output_key, result)
            return TaskResult.ok(output=result)


def _empty_result() -> dict:
    return {"shortlist": [], "memory_context": "", "has_memory": False, "lessons_context": ""}


async def _lessons_context(memory_store, goal: str) -> str:  # type: ignore[no-untyped-def]
    """Lessons from past incidents relevant to the goal; empty on any error (#175)."""
    try:
        return format_lessons_context(await memory_store.search_postmortems(goal, LESSONS_LIMIT))
    except Exception as e:  # noqa: BLE001 - lessons are advisory
        logger.warning("ConsultMemoryAction: lesson recall failed: %s", e)
        return ""
