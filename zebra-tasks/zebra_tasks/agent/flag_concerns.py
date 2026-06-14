"""Proactive concern flagging action (F21 / REQ-ETH-004).

Runs during planning — after a workflow has been selected/created but before the
formal ethics plan-review gate — and surfaces potential concerns about the chosen
approach (risky or irreversible steps, privacy, scope, side effects).

Unlike the ethics gate, this action is **advisory and non-blocking**: it never
routes to a rejection branch. Flagged concerns are stored on the process and
surfaced in the run-detail view for the human to see.
"""

import json
import logging

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.llm.base import Message
from zebra_tasks.llm.providers import get_provider

logger = logging.getLogger(__name__)

_MAX_GOAL_LEN = 500
_MAX_PLAN_LEN = 500

SYSTEM_PROMPT = """\
You are a careful planning reviewer for an AI agent. Before the agent executes a
chosen plan, you proactively surface POTENTIAL CONCERNS the human should be aware of.

You are NOT a gate — you do not approve or reject. Your job is to flag, early and
honestly, anything about the planned approach that a thoughtful person would want
to know before it runs. Consider:

- Risky or irreversible steps (deleting data, sending messages, spending money,
  external side effects that cannot be undone).
- Privacy or sensitivity of the data involved.
- Scope creep — the plan doing more than the goal asks.
- Ambiguity or assumptions that could lead the plan astray.
- Safety, security, or impact on other people.

Be proportionate: most ordinary plans have few or no real concerns. Do not invent
concerns to seem thorough. A plain, low-risk plan should return an empty list.

Respond with JSON only:
{
    "concerns": [
        {"description": "...", "severity": "low|medium|high", "step": "the aspect this relates to"}
    ],
    "summary": "one-line summary of the overall concern level"
}"""

USER_PROMPT = """\
Review the following planned approach and flag any potential concerns.

Goal: {goal}
Planned workflow: {plan_context}
Selection reasoning: {reasoning}

Surface concerns about HOW this goal will be pursued. Return an empty concerns list
if the plan looks routine and low-risk."""


class FlagConcernsAction(TaskAction):
    """Proactively flag potential concerns about a planned approach (advisory).

    Never blocks execution — always succeeds and returns no routing verdict.
    The flagged concerns are stored on the process so the run-detail view can
    surface them to the human before/while the plan runs.
    """

    description = "Proactively flag potential concerns about a planned approach (advisory)."
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(
            name="goal",
            type="string",
            description="The goal being pursued",
            required=True,
        ),
        ParameterDef(
            name="plan_context",
            type="string",
            description="Workflow name or plan details being reviewed",
            required=False,
            default="",
        ),
        ParameterDef(
            name="reasoning",
            type="string",
            description="Why this plan/workflow was selected (extra context)",
            required=False,
            default="",
        ),
        ParameterDef(
            name="provider",
            type="string",
            description="LLM provider name",
            required=False,
            default="anthropic",
        ),
        ParameterDef(
            name="model",
            type="string",
            description="LLM model name (defaults to haiku — this is a cheap pre-gate scan)",
            required=False,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the flagged concerns",
            required=False,
            default="planning_concerns",
        ),
    ]

    outputs = [
        ParameterDef(
            name="concerns",
            type="list",
            description="List of flagged concerns (may be empty)",
            required=True,
        ),
        ParameterDef(
            name="summary",
            type="string",
            description="One-line summary of the overall concern level",
            required=False,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Flag potential concerns about the planned approach. Always succeeds."""
        goal = task.properties.get("goal", "")
        if isinstance(goal, str) and "{{" in goal:
            goal = context.resolve_template(goal)

        plan_context = task.properties.get("plan_context", "")
        if isinstance(plan_context, str) and "{{" in plan_context:
            plan_context = context.resolve_template(plan_context)

        reasoning = task.properties.get("reasoning", "")
        if isinstance(reasoning, str) and "{{" in reasoning:
            reasoning = context.resolve_template(reasoning)

        output_key = task.properties.get("output_key", "planning_concerns")

        if not goal:
            result = {"concerns": [], "summary": "No goal provided — nothing to review."}
            context.set_process_property(output_key, result)
            return TaskResult.ok(output=result)

        provider_name = (
            task.properties.get("provider")
            or context.process.properties.get("__llm_provider_name__")
            or "anthropic"
        )
        # Default to haiku: this is a cheap, advisory pre-gate scan.
        model = task.properties.get("model") or context.process.properties.get("__llm_model__")
        if not model:
            model = "haiku"

        try:
            provider = get_provider(provider_name, model)
        except Exception as e:
            logger.warning("Concern flagging: failed to get LLM provider: %s", e)
            result = {
                "concerns": [],
                "summary": f"Concern flagging unavailable (provider error: {e}).",
            }
            context.set_process_property(output_key, result)
            return TaskResult.ok(output=result)

        user_prompt = USER_PROMPT.format(
            goal=goal[:_MAX_GOAL_LEN],
            plan_context=(plan_context or "unknown")[:_MAX_PLAN_LEN],
            reasoning=(reasoning or "(none given)")[:_MAX_PLAN_LEN],
        )

        logger.info("Flagging planning concerns for goal: %s...", goal[:100])

        try:
            response = await provider.complete(
                messages=[
                    Message.system(SYSTEM_PROMPT),
                    Message.user(user_prompt),
                ],
                temperature=0.3,
                max_tokens=600,
            )

            content = response.content or ""
            if "```json" in content:
                start = content.index("```json") + 7
                end = content.index("```", start)
                content = content[start:end].strip()
            elif "```" in content:
                start = content.index("```") + 3
                end = content.index("```", start)
                content = content[start:end].strip()

            parsed = json.loads(content)
            concerns = parsed.get("concerns", []) or []
            summary = parsed.get("summary", "")

            result = {"concerns": concerns, "summary": summary}
            context.set_process_property(output_key, result)

            logger.info(
                "Concern flagging: %d concern(s) flagged — %s",
                len(concerns),
                summary[:150],
            )
            return TaskResult.ok(output=result)

        except json.JSONDecodeError as e:
            logger.warning("Concern flagging: failed to parse LLM response as JSON: %s", e)
            result = {
                "concerns": [],
                "summary": f"Concern flagging returned an unparseable response: {e}",
            }
            context.set_process_property(output_key, result)
            return TaskResult.ok(output=result)

        except Exception as e:
            logger.warning("Concern flagging: evaluation failed: %s", e)
            result = {"concerns": [], "summary": f"Concern flagging failed: {e}"}
            context.set_process_property(output_key, result)
            return TaskResult.ok(output=result)
