"""PickEntriesForVerificationAction — select knowledge entries for human review."""

import logging

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

logger = logging.getLogger(__name__)


class PickEntriesForVerificationAction(TaskAction):
    """Select knowledge entries that need human verification.

    Returns entries where confidence is below ``low_confidence_threshold``
    or where ``last_verified`` is older than ``max_age_days``. Results are
    ordered by confidence ascending (lowest first), capped at ``max_entries``.

    Requires ``__knowledge_store__`` in ``context.extras`` and ``__user_id__``
    in process properties. Degrades gracefully when either is absent.

    Properties:
        low_confidence_threshold: Confidence below which an entry is flagged (default 0.6)
        max_age_days: Age in days after which an entry is flagged (default 90)
        max_entries: Maximum entries to return (default 5)
        output_key: Process property key for the result list (default "entries_to_verify")

    Output:
        - entries: list of dicts with id, category, key, value, confidence, last_verified
        - count: number of entries selected
    """

    description = "Select low-confidence or stale knowledge entries for human verification."

    inputs = [
        ParameterDef(
            name="low_confidence_threshold",
            type="float",
            description="Confidence threshold below which an entry needs verification",
            required=False,
            default=0.6,
        ),
        ParameterDef(
            name="max_age_days",
            type="integer",
            description="Age in days after which an entry needs verification",
            required=False,
            default=90,
        ),
        ParameterDef(
            name="max_entries",
            type="integer",
            description="Maximum number of entries to return",
            required=False,
            default=5,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key for the result",
            required=False,
            default="entries_to_verify",
        ),
    ]

    outputs = [
        ParameterDef(
            name="entries",
            type="list",
            description="Entries selected for verification",
            required=True,
        ),
        ParameterDef(
            name="count",
            type="integer",
            description="Number of entries selected",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        knowledge_store = context.extras.get("__knowledge_store__")
        _empty = TaskResult(
            success=True, output={"entries": [], "count": 0}, next_route="no_entries"
        )
        if knowledge_store is None:
            logger.info("PickEntriesForVerificationAction: no knowledge store — skipping")
            return _empty

        user_id = context.get_process_property("__user_id__")
        if user_id is None:
            logger.info("PickEntriesForVerificationAction: no user_id — skipping")
            return _empty

        low_confidence_threshold = float(task.properties.get("low_confidence_threshold", 0.6))
        max_age_days = int(task.properties.get("max_age_days", 90))
        max_entries = int(task.properties.get("max_entries", 5))
        output_key = task.properties.get("output_key", "entries_to_verify")

        try:
            entries = await knowledge_store.get_entries_for_verification(
                user_id=user_id,
                low_confidence_threshold=low_confidence_threshold,
                max_age_days=max_age_days,
                max_entries=max_entries,
            )

            serialized = [
                {
                    "id": e.id,
                    "category": e.category,
                    "key": e.key,
                    "value": e.value,
                    "confidence": e.confidence,
                    "last_verified": e.last_verified.isoformat(),
                }
                for e in entries
            ]

            result = {"entries": serialized, "count": len(serialized)}
            context.set_process_property(output_key, result)
            next_route = "has_entries" if serialized else "no_entries"
            logger.info(
                "PickEntriesForVerificationAction: selected %d entries for user %s (route=%s)",
                len(serialized),
                user_id,
                next_route,
            )
            return TaskResult(success=True, output=result, next_route=next_route)

        except Exception as e:
            logger.warning("PickEntriesForVerificationAction failed — degrading gracefully: %s", e)
            return _empty
