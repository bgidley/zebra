"""RecordEthicsRejectionAction — record which ethics gate rejected a goal, and why.

Runs on the Agent Main Loop's terminal ``ethics_rejection`` task. Every gate verdict is
already in the ethics audit trail; this action adds a per-run ``ethics_rejection``
process property so callers (``AgentLoop``) and the run pages can report the reason
instead of a generic failure (GitLab #143).
"""

import logging
from typing import Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

logger = logging.getLogger(__name__)


def format_ethics_rejection(rejection: dict[str, Any]) -> str:
    """One-line error message for a rejection record (used by AgentLoop and the web UI)."""
    return f"Rejected by ethics {rejection.get('gate', 'gate')}: {rejection.get('reasoning', '')}"


def infer_rejection(props: dict[str, Any]) -> dict[str, Any]:
    """Work out which gate rejected the goal from the main-loop process properties.

    The dilemma check comes first: on that path the plan assessment is also present
    (it escalated rather than rejected).
    """
    resolution = props.get("dilemma_resolution")
    plan = props.get("ethics_plan_assessment")
    if isinstance(resolution, dict) and resolution.get("route") == "reject":
        reasoning = "The ethics dilemma was declined by the user."
        if resolution.get("note"):
            reasoning = f"{reasoning} Note: {resolution['note']}"
        concerns = plan.get("concerns", []) if isinstance(plan, dict) else []
        return {"gate": "dilemma_resolution", "reasoning": reasoning, "concerns": concerns}

    if isinstance(plan, dict) and plan.get("approved") is False:
        gate, assessment = "plan_review", plan
    else:
        gate, assessment = "input_gate", props.get("ethics_input_assessment") or {}
    return {
        "gate": gate,
        "reasoning": str(assessment.get("overall_reasoning", "")),
        "concerns": list(assessment.get("concerns") or []),
    }


class RecordEthicsRejectionAction(TaskAction):
    """Store ``{gate, reasoning, concerns}`` for a rejected goal on the process."""

    description = "Record which ethics gate rejected the goal and its reasoning."
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the rejection record",
            required=False,
            default="ethics_rejection",
        ),
    ]

    outputs = [
        ParameterDef(
            name="gate",
            type="string",
            description="input_gate | plan_review | dilemma_resolution",
            required=True,
        ),
        ParameterDef(
            name="reasoning",
            type="string",
            description="Why the goal was rejected",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        output_key = task.properties.get("output_key", "ethics_rejection")
        rejection = infer_rejection(context.process.properties)
        context.set_process_property(output_key, rejection)
        logger.info(
            "Goal rejected by ethics %s: %s", rejection["gate"], rejection["reasoning"][:150]
        )
        return TaskResult.ok(output=rejection)
