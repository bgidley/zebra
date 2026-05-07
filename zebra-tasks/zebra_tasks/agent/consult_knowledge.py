"""ConsultKnowledgeAction - read personal knowledge store for LLM planning context."""

import logging

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

logger = logging.getLogger(__name__)


class ConsultKnowledgeAction(TaskAction):
    """
    Consult the personal knowledge store to produce context for the planning LLM.

    Reads knowledge entries for the current user from ``__knowledge_store__`` in
    ``context.extras``, formats them as a concise string, and stores the result
    in the process property named by ``output_key``.

    Degrades gracefully when the store is unavailable or ``user_id`` is ``None``.

    Properties:
        goal: The user's goal/request (used for logging only in this version)
        output_key: Where to store the result (default: "knowledge_context")

    Output:
        - knowledge: formatted context string (empty when no entries)
        - has_knowledge: bool indicating whether any knowledge was found

    Example workflow usage::

        tasks:
          consult_knowledge:
            name: "Consult Knowledge Store"
            action: consult_knowledge
            auto: true
            properties:
              goal: "{{goal}}"
              output_key: knowledge_context
    """

    description = "Read personal knowledge store entries for LLM planning context."

    inputs = [
        ParameterDef(
            name="goal",
            type="string",
            description="The user's goal/request",
            required=False,
            default="",
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the knowledge context result",
            required=False,
            default="knowledge_context",
        ),
    ]

    outputs = [
        ParameterDef(
            name="knowledge",
            type="string",
            description="Formatted personal knowledge context for LLM injection",
            required=True,
        ),
        ParameterDef(
            name="has_knowledge",
            type="bool",
            description="Whether any knowledge entries were found",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Read personal knowledge and return formatted context."""
        output_key = task.properties.get("output_key", "knowledge_context")

        knowledge_store = context.extras.get("__knowledge_store__")
        if knowledge_store is None:
            logger.info("No knowledge store available — returning empty context")
            result = {"knowledge": "", "has_knowledge": False}
            context.set_process_property(output_key, result)
            return TaskResult.ok(output=result)

        user_id = context.get_process_property("__user_id__")
        if user_id is None:
            logger.info("No user_id in process properties — returning empty knowledge context")
            result = {"knowledge": "", "has_knowledge": False}
            context.set_process_property(output_key, result)
            return TaskResult.ok(output=result)

        try:
            knowledge = await knowledge_store.get_context_for_llm(user_id)
            has_knowledge = bool(knowledge)

            if has_knowledge:
                entry_count = knowledge.count("\n") + 1
                logger.info(f"ConsultKnowledgeAction: {entry_count} entries for user {user_id}")
            else:
                logger.info(f"ConsultKnowledgeAction: no entries for user {user_id}")

            result = {"knowledge": knowledge, "has_knowledge": has_knowledge}
            context.set_process_property(output_key, result)
            return TaskResult.ok(output=result)

        except Exception as e:
            logger.warning(f"ConsultKnowledgeAction failed — degrading gracefully: {e}")
            result = {"knowledge": "", "has_knowledge": False}
            context.set_process_property(output_key, result)
            return TaskResult.ok(output=result)
