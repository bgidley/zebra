"""Propose trust promotion action (F15 / REQ-TRUST-004).

The agent's only sanctioned trust write path: it queues a pending suggestion
(domain, target level, supporting evidence) for the human to approve or reject.
It has no code path to ``set_trust_level`` — the agent can request more
autonomy, never grant it to itself.
"""

import logging

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

logger = logging.getLogger(__name__)


def _resolve(value, context: ExecutionContext):
    """Resolve {{template}} strings against the process properties."""
    if isinstance(value, str) and "{{" in value:
        return context.resolve_template(value)
    return value


class ProposeTrustPromotionAction(TaskAction):
    """Queue a trust promotion suggestion for human review.

    Reads ``__trust_store__`` from ``context.extras`` and calls
    ``add_suggestion`` — the suggestion is created ``pending`` and changes no
    trust level. Degrades gracefully (``submitted: False``) when the store is
    unavailable.
    """

    description = "Propose a trust level promotion for human approval (never self-promotes)."

    inputs = [
        ParameterDef(
            name="domain",
            type="string",
            description="Trust domain the promotion concerns (e.g. 'code')",
            required=True,
        ),
        ParameterDef(
            name="to_level",
            type="string",
            description="Suggested trust level: SEMI_AUTONOMOUS or AUTONOMOUS",
            required=True,
        ),
        ParameterDef(
            name="evidence",
            type="string",
            description="Supporting evidence shown to the human (supports {{var}} templates)",
            required=True,
        ),
        ParameterDef(
            name="user_id",
            type="number",
            description="User id; falls back to the __user_id__ process property",
            required=False,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the submission result",
            required=False,
            default="trust_promotion_proposal",
        ),
    ]

    outputs = [
        ParameterDef(
            name="submitted",
            type="bool",
            description="Whether a suggestion was queued",
            required=True,
        ),
        ParameterDef(
            name="suggestion_id",
            type="string",
            description="Id of the queued suggestion (when submitted)",
            required=False,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Queue the suggestion via the trust store."""
        domain = _resolve(task.properties.get("domain"), context)
        to_level = _resolve(task.properties.get("to_level"), context)
        evidence = _resolve(task.properties.get("evidence"), context)
        if not domain or not to_level or not evidence:
            return TaskResult.fail(
                "propose_trust_promotion requires 'domain', 'to_level', and 'evidence'"
            )

        raw_user_id = _resolve(task.properties.get("user_id"), context)
        if raw_user_id in (None, ""):
            raw_user_id = context.process.properties.get("__user_id__")
        try:
            user_id = int(raw_user_id) if raw_user_id not in (None, "") else None
        except (TypeError, ValueError):
            user_id = None
        if user_id is None:
            return TaskResult.fail("propose_trust_promotion: no resolvable user id")

        store = context.extras.get("__trust_store__")
        output_key = task.properties.get("output_key", "trust_promotion_proposal")
        if store is None:
            logger.warning(
                "propose_trust_promotion: __trust_store__ not available — suggestion skipped"
            )
            result = {"submitted": False, "suggestion_id": None}
            context.set_process_property(output_key, result)
            return TaskResult.ok(output=result)

        try:
            suggestion = await store.add_suggestion(user_id, domain, to_level, evidence)
        except ValueError as exc:
            return TaskResult.fail(f"propose_trust_promotion: {exc}")

        result = {
            "submitted": True,
            "suggestion_id": suggestion.id,
            "domain": domain,
            "to_level": str(suggestion.to_level),
            "status": suggestion.status,
        }
        context.set_process_property(output_key, result)
        logger.info("Trust promotion proposed: user=%s domain=%s -> %s", user_id, domain, to_level)
        return TaskResult.ok(output=result)
