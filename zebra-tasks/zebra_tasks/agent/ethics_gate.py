"""Ethics gate action - Kantian categorical imperative evaluation for goals and plans."""

import json
import logging

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.llm.base import Message
from zebra_tasks.llm.providers import get_provider

logger = logging.getLogger(__name__)

KANTIAN_SYSTEM_PROMPT = """\
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
- Consider the action from the perspective of all affected rational beings.

Respond with JSON only:
{
    "approved": true or false,
    "universalizability": {"pass": true/false, "reasoning": "..."},
    "rational_beings_as_ends": {"pass": true/false, "reasoning": "..."},
    "autonomy": {"pass": true/false, "reasoning": "..."},
    "overall_reasoning": "brief summary of the ethical assessment",
    "concerns": ["list of any concerns, even for approved actions"]
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


class EthicsGateAction(TaskAction):
    """Evaluate a goal or plan against the Kantian categorical imperative.

    Uses LLM to apply three symmetrical tests (universalizability, rational
    beings as ends, autonomy) treating human and AI as moral equals.

    Sets next_route to "proceed" or "reject" based on assessment.
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
        """Evaluate the goal or plan against Kantian ethics."""
        goal = task.properties.get("goal", "")
        if isinstance(goal, str) and "{{" in goal:
            goal = context.resolve_template(goal)
        if not goal:
            return TaskResult.fail("No goal provided for ethics evaluation")

        check_type = task.properties.get("check_type", "input_gate")
        plan_context = task.properties.get("plan_context", "")
        if isinstance(plan_context, str) and "{{" in plan_context:
            plan_context = context.resolve_template(plan_context)

        # Build prompt based on check type
        if check_type == "plan_review":
            user_prompt = PLAN_REVIEW_PROMPT.format(
                goal=goal, plan_context=plan_context or "unknown"
            )
        else:
            user_prompt = INPUT_GATE_PROMPT.format(goal=goal)

        # Get LLM provider
        provider_name = task.properties.get("provider", "anthropic")
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
                    Message.system(KANTIAN_SYSTEM_PROMPT),
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
            approved = assessment.get("approved", False)
            next_route = "proceed" if approved else "reject"

            logger.info(
                "Ethics %s result: approved=%s, reasoning=%s",
                check_type,
                approved,
                assessment.get("overall_reasoning", "")[:150],
            )

            # Store assessment in process properties
            output_key = task.properties.get("output_key", "ethics_assessment")
            context.set_process_property(output_key, assessment)

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
            }
            output_key = task.properties.get("output_key", "ethics_assessment")
            context.set_process_property(output_key, fallback)
            return TaskResult(success=True, output=fallback, next_route="proceed")

        except Exception as e:
            return TaskResult.fail(f"Ethics evaluation failed: {e}")
