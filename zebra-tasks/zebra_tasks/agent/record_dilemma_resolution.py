"""RecordDilemmaResolutionAction — record the human's resolution of an ethics dilemma.

Part of dilemma escalation (F22 / REQ-ETH-005). After the human resolves an escalated
ethics dilemma via the ``ethics_dilemma_resolution`` human task, this action records the
decision to the ethics audit trail, stores it on the process, and re-emits the decision
as a routing verdict (``proceed`` / ``reject``) so the workflow can continue.
"""

import logging

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

logger = logging.getLogger(__name__)

_MAX_REASONING_LEN = 500


class RecordDilemmaResolutionAction(TaskAction):
    """Record a human dilemma resolution and route on the chosen decision.

    Reads the ``decision`` (``proceed`` / ``decline``) and optional ``note`` from the
    ``ethics_dilemma_resolution`` human task output, appends an ethics-audit entry
    (``check_type="dilemma_resolution"``), stores the resolution on the process, and
    returns ``next_route`` = ``proceed`` (decision proceed) or ``reject`` (otherwise).

    Degrades gracefully when the audit store is absent — the routing decision is always
    honoured regardless of whether recording succeeds.
    """

    description = "Record the human's ethics-dilemma resolution and route accordingly."

    inputs = [
        ParameterDef(
            name="goal",
            type="string",
            description="The goal under evaluation (for the audit record)",
            required=False,
            default="",
        ),
        ParameterDef(
            name="resolution_task_id",
            type="string",
            description="Task definition id of the human resolution task to read",
            required=False,
            default="ethics_dilemma_resolution",
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the resolution record",
            required=False,
            default="dilemma_resolution",
        ),
    ]

    outputs = [
        ParameterDef(
            name="decision",
            type="string",
            description="The human's decision: proceed | decline",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        goal = task.properties.get("goal", "")
        if isinstance(goal, str) and "{{" in goal:
            goal = context.resolve_template(goal)

        resolution_task_id = task.properties.get("resolution_task_id", "ethics_dilemma_resolution")
        output_key = task.properties.get("output_key", "dilemma_resolution")

        human_output = context.get_task_output(resolution_task_id) or {}
        raw_decision = str(human_output.get("decision", "proceed")).strip().lower()
        decision = "proceed" if raw_decision == "proceed" else "decline"
        note = human_output.get("note", "")

        next_route = "proceed" if decision == "proceed" else "reject"

        record = {
            "decision": decision,
            "note": note,
            "route": next_route,
        }
        context.set_process_property(output_key, record)

        await self._write_audit(context, task, goal, decision, note)

        logger.info("Dilemma resolution recorded: decision=%s route=%s", decision, next_route)
        return TaskResult(success=True, output=record, next_route=next_route)

    async def _write_audit(
        self,
        context: ExecutionContext,
        task: TaskInstance,
        goal: str,
        decision: str,
        note: str,
    ) -> None:
        """Best-effort append to the ethics audit store; errors are logged, never raised."""
        audit_store = context.extras.get("__ethics_audit_store__")
        if audit_store is None:
            logger.info("Dilemma resolution: no ethics audit store — audit entry skipped")
            return
        raw_user_id = context.get_process_property("__user_id__")
        try:
            user_id = int(raw_user_id) if raw_user_id is not None else None
        except (TypeError, ValueError):
            user_id = None
        try:
            from zebra_agent.storage.interfaces import EthicsAuditEntry

            reasoning = f"Human resolved dilemma: {decision}."
            if note:
                reasoning = f"{reasoning} Note: {note}"
            entry = EthicsAuditEntry(
                process_id=task.process_id,
                goal=str(goal)[:_MAX_REASONING_LEN],
                approved=(decision == "proceed"),
                overall_reasoning=reasoning[:_MAX_REASONING_LEN],
                check_type="dilemma_resolution",
                user_id=user_id,
            )
            await audit_store.append(entry)
        except Exception as exc:
            logger.warning("Dilemma resolution: failed to write audit entry: %s", exc)
