"""ApplyResolutionAction — apply the user's contradiction resolution choice."""

import logging
from datetime import UTC, datetime

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

logger = logging.getLogger(__name__)


class ApplyResolutionAction(TaskAction):
    """Apply the user's choice from the resolve_contradiction human task.

    Reads the ``resolution`` field from the ``present_contradiction`` human task
    output and applies one of three strategies:

    - ``keep_existing``: no change, return ``{resolution: "kept_existing"}``
    - ``use_new``: call ``update_entry`` with the proposed value,
      return ``{resolution: "updated"}``
    - ``keep_both``: call ``add_entry`` with the key suffixed ``_alt``,
      return ``{resolution: "kept_both"}``

    Expects the following in process properties (set before this workflow starts):
    - ``entry_id``: ID of the existing entry to update
    - ``proposed_value``: the new value that was not stored
    - ``category``: knowledge category (needed for keep_both)
    - ``key``: knowledge key (needed for keep_both)
    - ``__user_id__``: user ID (needed for keep_both)

    Degrades gracefully when the knowledge store is absent.
    """

    description = "Apply the user's contradiction resolution to the knowledge store."

    inputs: list[ParameterDef] = []

    outputs = [
        ParameterDef(
            name="resolution",
            type="string",
            description="Applied resolution: kept_existing | updated | kept_both | skipped",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        from zebra_agent.knowledge import KnowledgeEntry

        knowledge_store = context.extras.get("__knowledge_store__")
        if knowledge_store is None:
            logger.info("ApplyResolutionAction: no knowledge store — skipping")
            return TaskResult.ok(output={"resolution": "skipped"})

        task_output = context.get_task_output("present_contradiction")
        if task_output is None:
            logger.info("ApplyResolutionAction: no human task output — skipping")
            return TaskResult.ok(output={"resolution": "skipped"})

        resolution = task_output.get("resolution", "keep_existing")
        entry_id = context.get_process_property("entry_id", "")
        proposed_value = context.get_process_property("proposed_value", "")
        category = context.get_process_property("category", "facts")
        key = context.get_process_property("key", "")
        user_id = context.get_process_property("__user_id__")

        try:
            if resolution == "keep_existing":
                logger.info("ApplyResolutionAction: keeping existing value for entry %s", entry_id)
                return TaskResult.ok(output={"resolution": "kept_existing"})

            elif resolution == "use_new":
                entry = await knowledge_store.get_entry(entry_id)
                if entry is not None:
                    entry.value = proposed_value
                    entry.confidence = 1.0
                    entry.last_verified = datetime.now(UTC)
                    entry.updated_at = datetime.now(UTC)
                    await knowledge_store.update_entry(entry)
                    logger.info(
                        "ApplyResolutionAction: updated entry %s to %r", entry_id, proposed_value
                    )
                return TaskResult.ok(output={"resolution": "updated"})

            elif resolution == "keep_both":
                if user_id is not None:
                    new_entry = KnowledgeEntry.create(
                        user_id=user_id,
                        category=category,
                        key=f"{key}_alt",
                        value=proposed_value,
                        source="human",
                    )
                    await knowledge_store.add_entry(new_entry)
                    logger.info(
                        "ApplyResolutionAction: added alt entry %s for key %r", new_entry.id, key
                    )
                return TaskResult.ok(output={"resolution": "kept_both"})

            else:
                logger.warning("ApplyResolutionAction: unknown resolution %r", resolution)
                return TaskResult.ok(output={"resolution": "skipped"})

        except Exception as e:
            logger.warning("ApplyResolutionAction failed — degrading gracefully: %s", e)
            return TaskResult.ok(output={"resolution": "skipped"})
