"""Continuation assessor action (F135).

When a goal continues a previous run, decide *how* to continue before anything
runs: re-run the same workflow, let the selector pick another existing workflow,
or have the creator generate a new one. Non-continuation goals pass straight
through (``not_continuation``) without an LLM call.
"""

import ast
import json
import logging
from typing import Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.agent.followup import (
    CONTINUATION_COMMENT_KEY,
    CONTINUATION_DECISION_KEY,
    CONTINUATION_RATIONALE_KEY,
    PREVIOUS_RUN_CONTEXT_KEY,
)
from zebra_tasks.llm.base import Message
from zebra_tasks.llm.providers import get_provider

logger = logging.getLogger(__name__)

SAME_WORKFLOW = "same_workflow"
EXISTING_WORKFLOW = "existing_workflow"
NEW_WORKFLOW = "new_workflow"
NOT_CONTINUATION = "not_continuation"
DECISIONS = (SAME_WORKFLOW, EXISTING_WORKFLOW, NEW_WORKFLOW)

_MAX_PROGRESS_ITEMS = 30

SYSTEM_PROMPT = """You decide how an AI agent should continue a previous run.

The user has asked to continue a run. Choose ONE:
- "same_workflow": re-run the previous workflow; it fits and the remaining work is
  more of the same (e.g. it failed transiently, or needs another pass with the
  user's comment as extra input).
- "existing_workflow": a different existing library workflow would better fit the
  remaining work; the selector will pick it.
- "new_workflow": the remaining work needs a workflow that doesn't exist yet.

Prefer "same_workflow" when the previous workflow is suitable. Prefer
"existing_workflow" over "new_workflow" unless the remaining work is clearly unlike
anything a general workflow can do.

Respond with JSON only:
{
  "decision": "same_workflow" | "existing_workflow" | "new_workflow",
  "rationale": "one or two sentences",
  "suggested_name": "Title Case name for a new workflow (only for new_workflow)"
}"""


def _format_progress(ctx: dict[str, Any]) -> str:
    """Render the previous run's task progress (F134), tolerating its absence."""
    progress = ctx.get("task_progress") or ctx.get("tasks")
    if not isinstance(progress, list) or not progress:
        return ""
    lines = []
    for item in progress[:_MAX_PROGRESS_ITEMS]:
        if isinstance(item, dict):
            name = item.get("task_name") or item.get("name") or item.get("task_id") or "task"
            state = item.get("state") or item.get("status") or ""
            lines.append(f"- {name}: {state}".rstrip(": "))
        else:
            lines.append(f"- {item}")
    return "Task progress:\n" + "\n".join(lines) + "\n"


def _parse_response(content: str) -> dict[str, Any]:
    """Extract the JSON object from an LLM reply (code fences tolerated)."""
    if "```" in content:
        start = content.index("```") + 3
        if content[start:].startswith("json"):
            start += 4
        end = content.find("```", start)
        content = content[start:] if end == -1 else content[start:end]
    data = json.loads(content.strip())
    if not isinstance(data, dict):
        raise ValueError("response is not a JSON object")
    return data


class ContinuationAssessorAction(TaskAction):
    """Decide how a continued goal should proceed: same, existing or new workflow.

    Routes:
        - ``not_continuation``  — no ``previous_run_context``; go to normal selection
        - ``same_workflow``     — re-run the previous run's workflow
        - ``existing_workflow`` — let the selector pick an existing workflow
        - ``new_workflow``      — let the creator generate a new workflow

    Sets process properties ``continuation_decision`` / ``continuation_rationale``
    (copied onto the WorkflowRun). For ``same_workflow`` it also sets
    ``workflow_name`` and a selector-shaped ``selection``; for ``new_workflow`` it
    sets ``selection`` with ``create_new: true``.
    """

    description = (
        "Assess how to continue a previous run: re-run the same workflow, select a "
        "different existing workflow, or create a new one."
    )
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(
            name="goal",
            type="string",
            description="The continuation goal",
            required=True,
        ),
        ParameterDef(
            name="available_workflows",
            type="list[dict]",
            description="Workflow info dicts; used to check the previous workflow exists "
            "when no WorkflowLibrary is available",
            required=False,
            default=[],
        ),
        ParameterDef(
            name="provider",
            type="string",
            description="LLM provider name",
            required=False,
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
            description="Process property key to store the assessment",
            required=False,
            default="continuation_assessment",
        ),
    ]

    outputs = [
        ParameterDef(
            name="decision",
            type="string",
            description="same_workflow | existing_workflow | new_workflow | not_continuation",
            required=True,
        ),
        ParameterDef(
            name="rationale",
            type="string",
            description="Short explanation of the decision",
            required=False,
        ),
        ParameterDef(
            name="workflow_name",
            type="string",
            description="Workflow to re-run (same_workflow only)",
            required=False,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Assess the continuation and route accordingly."""
        props = context.process.properties
        ctx = props.get(PREVIOUS_RUN_CONTEXT_KEY)
        if not isinstance(ctx, dict):
            return TaskResult(
                success=True,
                output={"decision": NOT_CONTINUATION},
                next_route=NOT_CONTINUATION,
            )

        goal = task.properties.get("goal") or props.get("goal") or ""
        if isinstance(goal, str) and "{{" in goal:
            goal = context.resolve_template(goal)
        comment = props.get(CONTINUATION_COMMENT_KEY) or ""
        previous_workflow = ctx.get("workflow_name") or ""

        decision, rationale, suggested_name = await self._assess(task, context, goal, ctx, comment)

        if decision == SAME_WORKFLOW and not self._workflow_exists(
            previous_workflow, task, context
        ):
            logger.warning(
                "Continuation chose same_workflow but %r is not in the library — "
                "falling back to existing_workflow",
                previous_workflow,
            )
            decision = EXISTING_WORKFLOW
            rationale = (
                f"{rationale} (Previous workflow '{previous_workflow}' is no longer "
                "available, so selecting an existing workflow instead.)"
            ).strip()

        context.set_process_property(CONTINUATION_DECISION_KEY, decision)
        context.set_process_property(CONTINUATION_RATIONALE_KEY, rationale)

        if decision == SAME_WORKFLOW:
            context.set_process_property("workflow_name", previous_workflow)
            context.set_process_property(
                "selection",
                {
                    "workflow_name": previous_workflow,
                    "create_new": False,
                    "create_variant": False,
                    "reasoning": rationale,
                    "suggested_name": None,
                },
            )
        elif decision == NEW_WORKFLOW:
            context.set_process_property(
                "selection",
                {
                    "workflow_name": None,
                    "create_new": True,
                    "create_variant": False,
                    "reasoning": rationale,
                    "suggested_name": suggested_name,
                },
            )

        output = {
            "decision": decision,
            "rationale": rationale,
            "workflow_name": previous_workflow if decision == SAME_WORKFLOW else None,
        }
        context.set_process_property(
            task.properties.get("output_key", "continuation_assessment"), output
        )
        logger.info("Continuation decision: %s — %s", decision, rationale[:150])
        return TaskResult(success=True, output=output, next_route=decision)

    async def _assess(
        self,
        task: TaskInstance,
        context: ExecutionContext,
        goal: str,
        ctx: dict[str, Any],
        comment: str,
    ) -> tuple[str, str, str | None]:
        """Ask the LLM for a decision; fall back to existing_workflow on any failure."""
        provider_name = (
            task.properties.get("provider")
            or context.process.properties.get("__llm_provider_name__")
            or "anthropic"
        )
        model = task.properties.get("model") or context.process.properties.get("__llm_model__")

        outcome = "succeeded" if ctx.get("success", True) else "failed"
        prompt = (
            f"Continuation goal: {goal}\n\n"
            f"User's comment on the previous run: {comment or '(none)'}\n\n"
            "<previous_run>\n"
            f"Goal: {ctx.get('goal', '')}\n"
            f"Workflow used: {ctx.get('workflow_name', '')}\n"
            f"Outcome: {outcome}\n"
            f"{_format_progress(ctx)}"
            f"Output:\n{ctx.get('output', '')}\n"
            "</previous_run>"
        )

        try:
            provider = get_provider(provider_name, model)
            response = await provider.complete(
                messages=[Message.system(SYSTEM_PROMPT), Message.user(prompt)],
                temperature=0.2,
                max_tokens=400,
            )
            data = _parse_response(response.content or "")
            decision = data.get("decision")
            if decision not in DECISIONS:
                raise ValueError(f"unknown decision {decision!r}")
            rationale = str(data.get("rationale") or "").strip()
            suggested = data.get("suggested_name") or None
            return decision, rationale, suggested
        except Exception as e:
            logger.warning("Continuation assessment failed (%s) — using existing_workflow", e)
            return (
                EXISTING_WORKFLOW,
                f"Assessment unavailable ({type(e).__name__}); defaulting to workflow selection.",
                None,
            )

    @staticmethod
    def _workflow_exists(name: str, task: TaskInstance, context: ExecutionContext) -> bool:
        """Check the previous workflow is still available."""
        if not name:
            return False
        library = context.extras.get("__workflow_library__")
        if library is not None:
            try:
                library.get_workflow(name)
                return True
            except Exception:
                return False

        workflows = task.properties.get("available_workflows") or []
        if isinstance(workflows, str):
            if "{{" in workflows:
                workflows = context.resolve_template(workflows)
            try:
                workflows = json.loads(workflows)
            except json.JSONDecodeError:
                try:
                    workflows = ast.literal_eval(workflows)
                except (ValueError, SyntaxError):
                    return False
        if not isinstance(workflows, list):
            return False
        names = {w.get("name") if isinstance(w, dict) else getattr(w, "name", w) for w in workflows}
        return name in names
