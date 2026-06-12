"""Trust gate action - per-domain trust level enforcement (F13 / REQ-TRUST-003).

Reads the (user, domain) trust level from the injected trust store and routes the
workflow: proceed when the agent's autonomy covers the action, or approve to send
the flow to a human approval task (the workflow's `auto: false` pause point).

The gate fails closed: when the trust level cannot be determined — no store, no
user, store error, unrecognised level — it behaves as SUPERVISED and requires
approval. Inability to verify trust never grants autonomy.
"""

import logging
from datetime import UTC, datetime

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

logger = logging.getLogger(__name__)

DECISIONS_KEY = "__trust_gate_decisions__"

# TrustLevel values from zebra_agent.storage.trust, compared as strings to keep
# zebra-tasks free of a zebra-agent dependency (TrustLevel is a StrEnum).
_SUPERVISED = "SUPERVISED"
_SEMI_AUTONOMOUS = "SEMI_AUTONOMOUS"
_AUTONOMOUS = "AUTONOMOUS"

ROUTE_PROCEED = "proceed"
ROUTE_APPROVE = "approve"


def _resolve(value, context: ExecutionContext):
    """Resolve {{template}} strings against the process properties."""
    if isinstance(value, str) and "{{" in value:
        return context.resolve_template(value)
    return value


class TrustGateAction(TaskAction):
    """Route a workflow based on the current per-domain trust level.

    Routing:
    - SUPERVISED: always ``approve`` — a human must approve every step.
    - SEMI_AUTONOMOUS: ``proceed`` only when the task declares
      ``reversibility: reversible``; anything else requires approval.
      (Contextual reversibility assessment arrives with F14.)
    - AUTONOMOUS: ``proceed``, logged.

    Every decision is appended to ``__trust_gate_decisions__`` in process
    properties and returned as the task output.
    """

    description = "Trust gate — pause for human approval when domain trust is insufficient."

    inputs = [
        ParameterDef(
            name="domain",
            type="string",
            description="Trust domain to check (e.g. 'code', 'finance')",
            required=True,
        ),
        ParameterDef(
            name="action_description",
            type="string",
            description="Human-readable description of the gated action",
            required=False,
            default="",
        ),
        ParameterDef(
            name="user_id",
            type="number",
            description="User id; falls back to the __user_id__ process property",
            required=False,
        ),
        ParameterDef(
            name="reversibility",
            type="string",
            description="Declared reversibility: 'reversible' or 'irreversible'",
            required=False,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the gate decision",
            required=False,
            default="trust_gate_decision",
        ),
    ]

    outputs = [
        ParameterDef(
            name="route",
            type="string",
            description="Chosen route: 'proceed' or 'approve'",
            required=True,
        ),
        ParameterDef(
            name="level",
            type="string",
            description="Trust level the decision was based on",
            required=True,
        ),
        ParameterDef(
            name="reason",
            type="string",
            description="Why the route was chosen",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Check the domain trust level and route to proceed or approve."""
        domain = _resolve(task.properties.get("domain"), context)
        if not domain:
            return TaskResult.fail("trust_gate requires a 'domain' property")

        action_description = _resolve(task.properties.get("action_description", ""), context)
        reversibility = _resolve(task.properties.get("reversibility"), context)

        user_id = self._resolve_user_id(task, context)
        level, level_reason = await self._read_level(user_id, domain, context)
        route, reason = self._decide(level, reversibility, level_reason)

        decision = {
            "task_id": task.id,
            "domain": domain,
            "user_id": user_id,
            "action_description": action_description or "",
            "level": level,
            "reversibility": reversibility,
            "route": route,
            "reason": reason,
            "decided_at": datetime.now(UTC).isoformat(),
        }

        decisions = list(context.process.properties.get(DECISIONS_KEY, []))
        decisions.append(decision)
        context.set_process_property(DECISIONS_KEY, decisions)

        output_key = task.properties.get("output_key", "trust_gate_decision")
        context.set_process_property(output_key, decision)

        logger.info(
            "Trust gate [%s] user=%s level=%s -> %s (%s)",
            domain,
            user_id,
            level,
            route,
            reason,
        )
        return TaskResult(success=True, output=decision, next_route=route)

    def _resolve_user_id(self, task: TaskInstance, context: ExecutionContext) -> int | None:
        """Resolve the user id from the task property, then __user_id__."""
        raw = _resolve(task.properties.get("user_id"), context)
        if raw in (None, ""):
            raw = context.process.properties.get("__user_id__")
        try:
            return int(raw) if raw not in (None, "") else None
        except (TypeError, ValueError):
            logger.warning("Trust gate: invalid user_id %r", raw)
            return None

    async def _read_level(
        self, user_id: int | None, domain: str, context: ExecutionContext
    ) -> tuple[str, str | None]:
        """Read the trust level, failing closed to SUPERVISED on any problem.

        Returns (level, reason) where reason is set when the level was forced
        to SUPERVISED rather than read from the store.
        """
        store = context.extras.get("__trust_store__")
        if store is None:
            logger.warning("Trust gate: __trust_store__ not available — failing closed")
            return _SUPERVISED, "trust store unavailable — failing closed"
        if user_id is None:
            logger.warning("Trust gate: no resolvable user id — failing closed")
            return _SUPERVISED, "no resolvable user id — failing closed"
        try:
            level = str(await store.get_trust_level(user_id, domain))
        except Exception as exc:
            logger.warning("Trust gate: trust store error (%s) — failing closed", exc)
            return _SUPERVISED, f"trust store error — failing closed: {exc}"
        if level not in (_SUPERVISED, _SEMI_AUTONOMOUS, _AUTONOMOUS):
            logger.warning("Trust gate: unrecognised level %r — failing closed", level)
            return _SUPERVISED, f"unrecognised trust level {level!r} — failing closed"
        return level, None

    @staticmethod
    def _decide(level: str, reversibility, forced_reason: str | None) -> tuple[str, str]:
        """Map (level, reversibility) to a route and human-readable reason."""
        if level == _AUTONOMOUS:
            return ROUTE_PROCEED, "domain is AUTONOMOUS"
        if level == _SEMI_AUTONOMOUS:
            if reversibility == "reversible":
                return ROUTE_PROCEED, "domain is SEMI_AUTONOMOUS and action is reversible"
            return (
                ROUTE_APPROVE,
                "domain is SEMI_AUTONOMOUS and action is not declared reversible",
            )
        return ROUTE_APPROVE, forced_reason or "domain is SUPERVISED"
