"""RecordEthicsReviewAction — persist the post-execution ethics review.

The Agent Main Loop's ``ethics_post_review`` step is a plain ``llm_call`` whose JSON
verdict lands in the ``ethics_post_assessment`` process property. This action
normalises that verdict, stores it back on the process, and appends it to the ethics
audit trail (``check_type="post_review"``) so the review is durable and visible
rather than discarded (GitLab #143).
"""

import logging
from typing import Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

logger = logging.getLogger(__name__)

_MAX_GOAL_LEN = 500
_MAX_REASONING_LEN = 2000


def normalise_post_review(raw: Any) -> dict[str, Any]:
    """Coerce an ``llm_call`` post-review output into a fixed-shape dict.

    ``llm_call`` with ``response_format: json`` returns the raw text when the response
    is not valid JSON. An unreadable review is not an endorsement, so it fails closed
    (``ethical=False``), consistent with the ethics gate (#118).
    """
    if not isinstance(raw, dict):
        return {
            "ethical": False,
            "overall_reasoning": "Post-execution review could not be parsed.",
            "concerns": ["Unparseable post-execution ethics review"],
            "recommendations": [],
        }
    return {
        "ethical": bool(raw.get("ethical", False)),
        "overall_reasoning": str(raw.get("overall_reasoning", "")),
        "concerns": [str(c) for c in raw.get("concerns") or []],
        "recommendations": [str(r) for r in raw.get("recommendations") or []],
    }


class RecordEthicsReviewAction(TaskAction):
    """Record the post-execution ethics review on the process and in the audit trail.

    Degrades gracefully: a missing audit store or a failed audit write is logged and
    the action still succeeds — the review is advisory and must never fail a goal.
    """

    description = "Normalise the post-execution ethics review and append it to the audit log."
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(
            name="assessment_key",
            type="string",
            description="Process property holding the raw post-review output",
            required=False,
            default="ethics_post_assessment",
        ),
    ]

    outputs = [
        ParameterDef(
            name="ethical",
            type="bool",
            description="Whether the completed action was judged ethical",
            required=True,
        ),
        ParameterDef(
            name="overall_reasoning",
            type="string",
            description="Summary reasoning for the verdict",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        key = task.properties.get("assessment_key", "ethics_post_assessment")
        review = normalise_post_review(context.get_process_property(key))
        context.set_process_property(key, review)

        await self._write_audit(context, task, review)
        logger.info("Post-execution ethics review recorded: ethical=%s", review["ethical"])
        return TaskResult.ok(output=review)

    async def _write_audit(
        self, context: ExecutionContext, task: TaskInstance, review: dict[str, Any]
    ) -> None:
        """Best-effort append to the ethics audit store; errors are logged, never raised."""
        audit_store = context.extras.get("__ethics_audit_store__")
        if audit_store is None:
            logger.warning("Post-review: __ethics_audit_store__ not available — audit skipped")
            return
        raw_user_id = context.get_process_property("__user_id__")
        try:
            user_id = int(raw_user_id) if raw_user_id is not None else None
        except (TypeError, ValueError):
            user_id = None
        try:
            from zebra_agent.storage.interfaces import EthicsAuditEntry

            entry = EthicsAuditEntry(
                process_id=task.process_id,
                goal=str(context.get_process_property("goal", ""))[:_MAX_GOAL_LEN],
                approved=review["ethical"],
                overall_reasoning=review["overall_reasoning"][:_MAX_REASONING_LEN],
                check_type="post_review",
                user_id=user_id,
            )
            await audit_store.append(entry)
        except Exception as exc:
            logger.error("Post-review: failed to write audit entry: %s", exc)
