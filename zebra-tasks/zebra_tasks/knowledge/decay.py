"""DecayConfidenceAction — apply exponential confidence decay to time-sensitive knowledge."""

import logging
import math
from datetime import UTC, datetime

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

logger = logging.getLogger(__name__)


class DecayConfidenceAction(TaskAction):
    """Apply exponential half-life confidence decay to time-sensitive knowledge entries.

    For each entry where ``time_sensitive=True``, reduces confidence using:

        new_confidence = max(floor, confidence * 0.5 ^ (days_elapsed / half_life_days))

    Entries with ``category="history"`` (half-life = None) are skipped.
    Requires ``__knowledge_store__`` and ``__user_id__`` in context.

    Properties:
        None required. Reads ``__user_id__`` from process properties.

    Output:
        - decayed: number of entries whose confidence was updated
        - skipped: number of entries skipped (not time-sensitive or no half-life)
    """

    description = "Apply exponential confidence decay to time-sensitive knowledge entries."

    inputs = []

    outputs = [
        ParameterDef(
            name="decayed",
            type="integer",
            description="Number of entries whose confidence was reduced",
            required=True,
        ),
        ParameterDef(
            name="skipped",
            type="integer",
            description="Number of entries skipped",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        from zebra_agent.knowledge import CATEGORY_DECAY_HALF_LIFE_DAYS, CONFIDENCE_DECAY_FLOOR

        knowledge_store = context.extras.get("__knowledge_store__")
        if knowledge_store is None:
            logger.info("DecayConfidenceAction: no knowledge store — skipping")
            return TaskResult.ok(output={"decayed": 0, "skipped": 0})

        user_id = context.get_process_property("__user_id__")
        if user_id is None:
            logger.info("DecayConfidenceAction: no user_id — skipping")
            return TaskResult.ok(output={"decayed": 0, "skipped": 0})

        try:
            entries = await knowledge_store.get_entries(user_id)
            now = datetime.now(UTC)
            decayed = 0
            skipped = 0

            for entry in entries:
                if not entry.time_sensitive:
                    skipped += 1
                    continue

                half_life = CATEGORY_DECAY_HALF_LIFE_DAYS.get(entry.category)
                if half_life is None:
                    skipped += 1
                    continue

                days_elapsed = (now - entry.last_verified).total_seconds() / 86400.0
                if days_elapsed <= 0:
                    skipped += 1
                    continue

                new_confidence = entry.confidence * math.pow(0.5, days_elapsed / half_life)
                new_confidence = max(CONFIDENCE_DECAY_FLOOR, new_confidence)

                if abs(new_confidence - entry.confidence) < 0.001:
                    skipped += 1
                    continue

                entry.confidence = new_confidence
                await knowledge_store.update_entry(entry)
                decayed += 1

            logger.info(
                "DecayConfidenceAction: decayed=%d skipped=%d for user %s",
                decayed,
                skipped,
                user_id,
            )
            return TaskResult.ok(output={"decayed": decayed, "skipped": skipped})

        except Exception as e:
            logger.warning("DecayConfidenceAction failed — degrading gracefully: %s", e)
            return TaskResult.ok(output={"decayed": 0, "skipped": 0})
