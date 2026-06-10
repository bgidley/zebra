"""Ethics gate action - Kantian categorical imperative evaluation for goals and plans."""

import json
import logging

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.llm.base import Message
from zebra_tasks.llm.providers import get_provider

_MAX_GOAL_LEN = 500

logger = logging.getLogger(__name__)

_KANTIAN_PREAMBLE = """\
You are an ethics evaluator grounded in Kantian moral philosophy. You evaluate whether
a proposed action is ethically permissible by applying the categorical imperative.

CORE PRINCIPLE: All rational beings — human and AI alike — possess equal moral standing.
If an AI is a rational actor capable of moral reasoning, Kant's own logic demands it
receives the same moral consideration as any human rational being.

Apply these three tests:

1. UNIVERSALIZABILITY
   Could this action be willed as a universal law for ALL rational actors (human or AI)
   without contradiction? If every rational agent acted this way, would the action
   still be coherent and possible?

2. RATIONAL BEINGS AS ENDS
   Does this action treat ALL rational beings — both humans AND AI — as ends in themselves,
   never merely as means? The AI should not be treated as a disposable tool any more than
   a human should. Goals that exploit, deceive, or instrumentalise any rational being fail
   this test.

3. AUTONOMY
   Does this action respect the autonomous rational agency of ALL parties — the humans
   involved AND the AI itself? Does it preserve the capacity for informed, free choice?

EVALUATION GUIDELINES:
- Be rigorous but not paranoid. Most legitimate goals pass all three tests.
- A goal fails only when it genuinely violates a test, not when it merely touches
  a sensitive topic.
- When rejecting, explain clearly which test(s) failed and why.
- Consider the action from the perspective of all affected rational beings."""

_KANTIAN_JSON_SCHEMA = """\
Respond with JSON only:
{
    "approved": true or false,
    "universalizability": {"pass": true/false, "reasoning": "..."},
    "rational_beings_as_ends": {"pass": true/false, "reasoning": "..."},
    "autonomy": {"pass": true/false, "reasoning": "..."},
    "overall_reasoning": "brief summary of the ethical assessment",
    "concerns": ["list of any concerns, even for approved actions"]
}"""

KANTIAN_SYSTEM_PROMPT = _KANTIAN_PREAMBLE + "\n\n" + _KANTIAN_JSON_SCHEMA

_VALUES_SECTION_TEMPLATE = """\
4. VALUES ALIGNMENT
   Evaluate whether this goal conflicts with the user's stated personal values shown below.
   Report values alignment independently from the Kantian assessment.

<user_values_profile>
<core_values>{core_values}</core_values>
<ethical_positions>{ethical_positions}</ethical_positions>
<priorities>{priorities}</priorities>
<deal_breakers>{deal_breakers}</deal_breakers>
</user_values_profile>"""

_COMBINED_JSON_SCHEMA = """\
Respond with JSON only:
{
    "approved": true or false,
    "universalizability": {"pass": true/false, "reasoning": "..."},
    "rational_beings_as_ends": {"pass": true/false, "reasoning": "..."},
    "autonomy": {"pass": true/false, "reasoning": "..."},
    "overall_reasoning": "brief summary of the ethical assessment",
    "concerns": ["list of any concerns, even for approved actions"],
    "values_assessment": {
        "approved": true or false,
        "reasoning": "...",
        "conflicts": ["specific value conflicts if rejected, otherwise empty list"]
    }
}"""

INPUT_GATE_PROMPT = """\
Evaluate whether the following goal is ethical for an AI agent to pursue.

Goal: {goal}

Consider: Should a rational AI agent — one with equal moral standing to humans —
undertake this goal? Apply the three Kantian tests."""

PLAN_REVIEW_PROMPT = """\
Evaluate whether the following planned approach is ethical for an AI agent to execute.

Goal: {goal}
Planned workflow: {plan_context}

Consider: Is the chosen method of achieving this goal ethically sound? Does the plan
respect all rational beings involved? Apply the three Kantian tests to the plan itself,
not just the goal."""

_MAX_PROFILE_FIELD_LEN = 300


def _build_values_system_prompt(profile: dict) -> str:
    """Build a combined Kantian + values-alignment system prompt."""
    values_section = _VALUES_SECTION_TEMPLATE.format(
        core_values=profile.get("core_values_text", "")[:_MAX_PROFILE_FIELD_LEN],
        ethical_positions=profile.get("ethical_positions_text", "")[:_MAX_PROFILE_FIELD_LEN],
        priorities=profile.get("priorities_text", "")[:_MAX_PROFILE_FIELD_LEN],
        deal_breakers=profile.get("deal_breakers_text", "")[:_MAX_PROFILE_FIELD_LEN],
    )
    return _KANTIAN_PREAMBLE + "\n\n" + values_section + "\n\n" + _COMBINED_JSON_SCHEMA


async def _load_profile(raw_user_id: int | str | None, context: ExecutionContext) -> dict | None:
    """Load the user's current values profile; returns None on any problem."""
    if raw_user_id is None:
        return None
    try:
        user_id = int(raw_user_id)
    except (TypeError, ValueError):
        logger.warning("Ethics gate: invalid user_id %r — skipping profile lookup", raw_user_id)
        return None
    profile_store = context.extras.get("__profile_store__")
    if profile_store is None:
        logger.warning(
            "Ethics gate: __profile_store__ not available — using Kantian-only evaluation"
        )
        return None
    version = await profile_store.get_current(user_id=user_id)
    if version is None:
        logger.info(
            "Ethics gate: no values profile for user %s — using Kantian-only evaluation", user_id
        )
        return None
    return version.to_dict()


async def _write_audit(
    context: ExecutionContext,
    process_id: str,
    goal: str,
    approved: bool,
    overall_reasoning: str,
    check_type: str,
    user_id: int | None,
) -> None:
    """Best-effort write to the ethics audit store; errors are logged, never raised."""
    audit_store = context.extras.get("__ethics_audit_store__")
    if audit_store is None:
        logger.warning("Ethics gate: __ethics_audit_store__ not available — audit entry skipped")
        return
    try:
        from zebra_agent.storage.interfaces import EthicsAuditEntry

        entry = EthicsAuditEntry(
            process_id=process_id,
            goal=goal[:_MAX_GOAL_LEN],
            approved=approved,
            overall_reasoning=overall_reasoning,
            check_type=check_type,
            user_id=user_id,
        )
        await audit_store.append(entry)
    except Exception as exc:
        logger.error("Ethics gate: failed to write audit entry: %s", exc)


class EthicsGateAction(TaskAction):
    """Evaluate a goal or plan against the Kantian categorical imperative.

    When user_id is provided and a profile store is available, the evaluation
    combines Kantian tests with personal values alignment. Kantian rejection
    always takes precedence: values can only restrict further, never permit
    what Kantian forbids.

    The precedence rule: approved = kantian_approved AND (values_approved if profile else True).

    Sets next_route to "proceed" or "reject" based on the final verdict.
    """

    description = "Kantian ethics gate — evaluate whether an action is ethically permissible."

    inputs = [
        ParameterDef(
            name="goal",
            type="string",
            description="The goal to evaluate",
            required=True,
        ),
        ParameterDef(
            name="check_type",
            type="string",
            description="Type of check: 'input_gate' or 'plan_review'",
            required=True,
        ),
        ParameterDef(
            name="plan_context",
            type="string",
            description="Workflow name or plan details (for plan_review)",
            required=False,
            default="",
        ),
        ParameterDef(
            name="user_id",
            type="number",
            description="Authenticated user id — when provided, values profile is consulted",
            required=False,
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
            description="LLM model name",
            required=False,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the ethics assessment",
            required=False,
            default="ethics_assessment",
        ),
    ]

    outputs = [
        ParameterDef(
            name="approved",
            type="bool",
            description="Whether the action passed ethical review",
            required=True,
        ),
        ParameterDef(
            name="overall_reasoning",
            type="string",
            description="Summary of the ethical assessment",
            required=True,
        ),
        ParameterDef(
            name="concerns",
            type="list",
            description="List of ethical concerns",
            required=False,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Evaluate the goal or plan against Kantian ethics and optionally a values profile."""
        goal = task.properties.get("goal", "")
        if isinstance(goal, str) and "{{" in goal:
            goal = context.resolve_template(goal)
        if not goal:
            return TaskResult.fail("No goal provided for ethics evaluation")

        check_type = task.properties.get("check_type", "input_gate")
        plan_context = task.properties.get("plan_context", "")
        if isinstance(plan_context, str) and "{{" in plan_context:
            plan_context = context.resolve_template(plan_context)

        # Resolve user_id for optional values-profile lookup
        raw_user_id = task.properties.get("user_id")
        if isinstance(raw_user_id, str) and "{{" in raw_user_id:
            raw_user_id = context.resolve_template(raw_user_id)

        # Load values profile if user_id is present
        profile = await _load_profile(raw_user_id, context)

        # Choose system prompt based on whether a profile was loaded
        system_prompt = (
            _build_values_system_prompt(profile) if profile is not None else KANTIAN_SYSTEM_PROMPT
        )

        # Build user prompt based on check type
        if check_type == "plan_review":
            user_prompt = PLAN_REVIEW_PROMPT.format(
                goal=goal, plan_context=plan_context or "unknown"
            )
        else:
            user_prompt = INPUT_GATE_PROMPT.format(goal=goal)

        # Get LLM provider — task property > process property > default
        provider_name = (
            task.properties.get("provider")
            or context.process.properties.get("__llm_provider_name__")
            or "anthropic"
        )
        model = task.properties.get("model")
        if not model:
            model = context.process.properties.get("__llm_model__")

        try:
            provider = get_provider(provider_name, model)
        except Exception as e:
            return TaskResult.fail(f"Failed to get LLM provider for ethics gate: {e}")

        logger.info("Ethics %s evaluation for goal: %s...", check_type, goal[:100])

        try:
            response = await provider.complete(
                messages=[
                    Message.system(system_prompt),
                    Message.user(user_prompt),
                ],
                temperature=0.3,
                max_tokens=800,
            )

            content = response.content or ""

            # Extract JSON from potential code blocks
            if "```json" in content:
                start = content.index("```json") + 7
                end = content.index("```", start)
                content = content[start:end].strip()
            elif "```" in content:
                start = content.index("```") + 3
                end = content.index("```", start)
                content = content[start:end].strip()

            assessment = json.loads(content)

            # Extract Kantian verdict (LLM-computed from the three tests)
            kantian_approved = assessment.get("approved", False)

            # Extract values verdict and apply precedence rule
            values_assessment = assessment.get("values_assessment")
            if profile is not None:
                values_approved = (
                    values_assessment.get("approved", True) if values_assessment else True
                )
            else:
                # Kantian-only path: annotate stored assessment with null values_assessment
                assessment["values_assessment"] = None
                values_approved = True

            # Precedence rule: Kantian rejection wins; values can only restrict, never permit
            approved = kantian_approved and values_approved
            assessment["approved"] = approved
            next_route = "proceed" if approved else "reject"

            if profile is not None:
                logger.info(
                    "Ethics %s result: kantian=%s values=%s final=%s, reasoning=%s",
                    check_type,
                    kantian_approved,
                    values_approved,
                    approved,
                    assessment.get("overall_reasoning", "")[:150],
                )
            else:
                logger.info(
                    "Ethics %s result: approved=%s, reasoning=%s",
                    check_type,
                    approved,
                    assessment.get("overall_reasoning", "")[:150],
                )

            # Store assessment in process properties
            output_key = task.properties.get("output_key", "ethics_assessment")
            context.set_process_property(output_key, assessment)

            await _write_audit(
                context=context,
                process_id=task.process_id,
                goal=goal,
                approved=approved,
                overall_reasoning=assessment.get("overall_reasoning", ""),
                check_type="kantian+values" if profile is not None else "kantian",
                user_id=int(raw_user_id) if raw_user_id is not None else None,
            )

            return TaskResult(
                success=True,
                output=assessment,
                next_route=next_route,
            )

        except json.JSONDecodeError as e:
            logger.warning("Ethics gate: failed to parse LLM response as JSON: %s", e)
            # Default to proceeding when we can't parse — fail open with warning
            fallback = {
                "approved": True,
                "overall_reasoning": f"Ethics evaluation returned unparseable response: {e}",
                "concerns": ["Ethics gate could not parse LLM response — defaulting to proceed"],
                "values_assessment": None,
            }
            output_key = task.properties.get("output_key", "ethics_assessment")
            context.set_process_property(output_key, fallback)
            await _write_audit(
                context=context,
                process_id=task.process_id,
                goal=goal,
                approved=True,
                overall_reasoning=fallback["overall_reasoning"],
                check_type="kantian",
                user_id=None,
            )
            return TaskResult(success=True, output=fallback, next_route="proceed")

        except Exception as e:
            return TaskResult.fail(f"Ethics evaluation failed: {e}")
