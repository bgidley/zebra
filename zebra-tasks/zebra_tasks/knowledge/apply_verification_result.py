"""ApplyVerificationResultAction — apply the human's verification choices."""

import logging
from datetime import UTC, datetime

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

logger = logging.getLogger(__name__)


class ApplyVerificationResultAction(TaskAction):
    """Apply the user's answer from the knowledge verification human task.

    Reads the ``action`` field from the ``verify_entries`` human task output:

    - ``still_correct``: refreshes ``last_verified`` and resets ``confidence``
      to 1.0 for all entries that were presented.
    - ``skip``: no changes.

    Requires ``__knowledge_store__`` in ``context.extras``.
    Degrades gracefully when the store is absent.
    """

    description = "Apply the user's verification choices to knowledge entries."

    inputs: list[ParameterDef] = []

    outputs = [
        ParameterDef(
            name="verified",
            type="integer",
            description="Number of entries marked still-correct",
            required=True,
        ),
        ParameterDef(
            name="updated",
            type="integer",
            description="Number of entries updated with new values",
            required=True,
        ),
        ParameterDef(
            name="deleted",
            type="integer",
            description="Number of entries soft-deleted",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        knowledge_store = context.extras.get("__knowledge_store__")
        if knowledge_store is None:
            logger.info("ApplyVerificationResultAction: no knowledge store — skipping")
            return TaskResult.ok(output={"verified": 0, "updated": 0, "deleted": 0})

        task_output = context.get_task_output("verify_entries")
        action = task_output.get("action", "skip") if task_output else "skip"

        if action != "still_correct":
            return TaskResult.ok(output={"verified": 0, "updated": 0, "deleted": 0})

        entries_data = context.get_process_property("entries_to_verify", {})
        entries_list = entries_data.get("entries", []) if isinstance(entries_data, dict) else []
        verified = 0

        try:
            now = datetime.now(UTC)
            for entry_dict in entries_list:
                entry = await knowledge_store.get_entry(entry_dict["id"])
                if entry is not None and not entry.is_deleted:
                    entry.last_verified = now
                    entry.confidence = 1.0
                    entry.updated_at = now
                    await knowledge_store.update_entry(entry)
                    verified += 1

            logger.info("ApplyVerificationResultAction: verified %d entries", verified)
            return TaskResult.ok(output={"verified": verified, "updated": 0, "deleted": 0})

        except Exception as e:
            logger.warning("ApplyVerificationResultAction failed — degrading gracefully: %s", e)
            return TaskResult.ok(output={"verified": 0, "updated": 0, "deleted": 0})
