"""The "I'm stuck" handoff: ask a human for help instead of failing (#176).

When the Agent Main Loop's goal workflow fails, ``assess_stuck`` parks the goal on
the ``stuck_help_request`` human task with a short help request (what I tried,
where I'm stuck, what I need), while the help budget lasts. ``apply_help_response``
then routes on the human's answer: ``retry`` the same workflow with their
guidance, ``redirect`` to a new goal, or ``abandon`` (record and fail, as #140).

The human's answers are kept in ``__help_history__``; :func:`with_help_guidance`
appends them to the goal the next goal workflow sees, so ``goal`` itself stays as
the user typed it.
"""

import json
import logging
from typing import Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.agent.voice import VOICE_SCHEMA_FIELDS, voice_fields
from zebra_tasks.llm.base import Message
from zebra_tasks.llm.providers import get_provider
from zebra_tasks.llm.providers.registry import default_provider_name

logger = logging.getLogger(__name__)

HELP_REQUESTS_KEY = "__help_requests__"
HELP_HISTORY_KEY = "__help_history__"
HELP_DISPLAY_KEY = "help_request_display"
DEFAULT_MAX_HELP_REQUESTS = 2
DECISIONS = ("retry", "redirect", "abandon")
ABANDONED_SUFFIX = " (abandoned after asking for help)"

_MAX_GOAL_CHARS = 1000
_MAX_ERROR_CHARS = 1000
_MAX_TASKS = 15
_MAX_TASK_TEXT_CHARS = 200
_MAX_GUIDANCE_CHARS = 2000

SYSTEM_PROMPT = (
    """\
You are Zebra, an AI agent. You just tried to achieve a user's goal and the workflow
failed. Instead of giving up, you are asking the user for help.

Write a short, honest help request in the first person:
- tried: what you attempted (the workflow and the steps that ran), one or two sentences
- stuck_on: where and why it went wrong, in plain words, one or two sentences
- need: the specific thing from the user that would most likely get you unstuck
  (a missing detail, a decision, a different approach, or permission to stop)

Be concrete. Do not apologise at length or invent progress that did not happen.

Respond with JSON only:
{
    "tried": "...",
    "stuck_on": "...",
    "need": "...",
"""
    + VOICE_SCHEMA_FIELDS
    + """
}"""
)

USER_PROMPT = """\
Goal: {goal}
Workflow used: {workflow_name}
Error: {error}
Steps that ran:
{tasks}"""


def _as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes")
    return bool(value)


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _task_lines(executions: Any) -> str:
    """Summarise the failed child's task executions, one line per step."""
    if not isinstance(executions, list) or not executions:
        return "(no steps recorded)"
    lines = []
    for ex in executions[-_MAX_TASKS:]:
        if not isinstance(ex, dict):
            continue
        detail = ex.get("error") or ex.get("output") or ""
        line = f"- {ex.get('task_name', '?')} [{ex.get('state', '?')}]"
        if detail:
            line += f": {str(detail)[:_MAX_TASK_TEXT_CHARS]}"
        lines.append(line)
    return "\n".join(lines) or "(no steps recorded)"


def render_help_request(request: dict[str, Any]) -> str:
    """Format a help request for the read-only form field."""
    return (
        f"What I tried: {request.get('tried', '')}\n\n"
        f"Where I'm stuck: {request.get('stuck_on', '')}\n\n"
        f"What I need from you: {request.get('need', '')}"
    )


def with_help_guidance(goal: str, properties: dict[str, Any]) -> str:
    """Return *goal* followed by earlier failed attempts and the human's guidance.

    Args:
        goal: The goal to run.
        properties: Process properties (checked for ``__help_history__``).

    Returns:
        The goal unchanged when no help was given; otherwise the goal followed by
        a delimited list of earlier failures and what the user said about them.
    """
    history = properties.get(HELP_HISTORY_KEY)
    entries = [h for h in history or [] if isinstance(h, dict) and h.get("decision") != "abandon"]
    if not entries:
        return goal
    lines = [
        goal,
        "",
        "Earlier attempts at this goal failed and the user was asked for help. "
        "Use their guidance; do not repeat what failed.",
        "<help_history>",
    ]
    for n, h in enumerate(entries, start=1):
        lines.append(f"Attempt {n} failed: {h.get('error') or 'unknown error'}")
        if h.get("decision") == "redirect":
            lines.append(f"The user redirected the goal from: {h.get('previous_goal', '')}")
        elif h.get("guidance"):
            lines.append(f"User guidance: {h['guidance']}")
    lines.append("</help_history>")
    return "\n".join(lines)


class AssessStuckAction(TaskAction):
    """Route a failed goal run to a human help request while the budget lasts.

    Routes ``proceed`` when the goal workflow succeeded or the help budget is
    spent, and ``ask_human`` otherwise, after storing the help request
    (``output_key``) and its display text (``help_request_display``). Never fails:
    without an LLM the request is built from the error.
    """

    description = "Ask a human for help when the goal workflow failed (I'm stuck handoff)."
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(
            name="goal", type="string", description="The goal being pursued", required=True
        ),
        ParameterDef(
            name="workflow_name",
            type="string",
            description="The goal workflow that ran",
            required=False,
            default="",
        ),
        ParameterDef(
            name="success",
            type="bool",
            description="Whether the goal workflow succeeded",
            required=True,
        ),
        ParameterDef(
            name="error",
            type="string",
            description="The goal workflow's error",
            required=False,
            default="",
        ),
        ParameterDef(
            name="max_help_requests",
            type="int",
            description="Help requests allowed per goal before failing as usual",
            required=False,
            default=DEFAULT_MAX_HELP_REQUESTS,
        ),
        ParameterDef(
            name="model",
            type="string",
            description="LLM model for the help request (default haiku)",
            required=False,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key for the help request",
            required=False,
            default="help_request",
        ),
    ]

    outputs = [
        ParameterDef(
            name="stuck",
            type="bool",
            description="True when the goal was routed to a human",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        props = task.properties
        output_key = props.get("output_key", "help_request")
        success = _as_bool(context.resolve_template(str(props.get("success", "False"))))
        if success:
            return TaskResult(success=True, output={"stuck": False}, next_route="proceed")

        asked = _as_int(context.get_process_property(HELP_REQUESTS_KEY, 0), 0)
        limit = _as_int(props.get("max_help_requests"), DEFAULT_MAX_HELP_REQUESTS)
        if asked >= limit:
            logger.info("Goal failed; help budget spent (%d/%d), not asking", asked, limit)
            return TaskResult(
                success=True,
                output={"stuck": False, "help_budget_spent": True},
                next_route="proceed",
            )

        goal = context.resolve_template(str(props.get("goal", "")))
        workflow_name = context.resolve_template(str(props.get("workflow_name", "")))
        error = context.resolve_template(str(props.get("error", "")))
        if error in ("", "None"):
            error = "unknown error"
        executions = context.get_process_property("__task_executions__", [])

        request = await self._write_request(task, context, goal, workflow_name, error, executions)
        request["error"] = error[:_MAX_ERROR_CHARS]
        request["attempt"] = asked + 1
        context.set_process_property(HELP_REQUESTS_KEY, asked + 1)
        context.set_process_property(output_key, request)
        context.set_process_property(HELP_DISPLAY_KEY, render_help_request(request))
        logger.info("Goal stuck (request %d/%d); asking a human for help", asked + 1, limit)
        return TaskResult(success=True, output={"stuck": True, **request}, next_route="ask_human")

    async def _write_request(
        self,
        task: TaskInstance,
        context: ExecutionContext,
        goal: str,
        workflow_name: str,
        error: str,
        executions: Any,
    ) -> dict[str, Any]:
        """Ask a cheap model to write the help request; fall back to a plain one."""
        fallback = {
            "tried": f"I ran the '{workflow_name or 'selected'}' workflow for your goal.",
            "stuck_on": f"It failed: {error[:_MAX_ERROR_CHARS]}",
            "need": "Tell me how to fix this and I'll retry, give me a different goal, "
            "or tell me to stop.",
        }
        provider_name = (
            context.get_process_property("__llm_provider_name__") or default_provider_name()
        )
        # A cheap model: this is a short note to the user, not the goal's work.
        model = task.properties.get("model") or "haiku"
        try:
            provider = get_provider(provider_name, model)
            response = await provider.complete(
                messages=[
                    Message.system(SYSTEM_PROMPT),
                    Message.user(
                        USER_PROMPT.format(
                            goal=goal[:_MAX_GOAL_CHARS],
                            workflow_name=workflow_name or "unknown",
                            error=error[:_MAX_ERROR_CHARS],
                            tasks=_task_lines(executions),
                        )
                    ),
                ],
                temperature=0.3,
                max_tokens=500,
            )
            _track_cost(context, response, getattr(provider, "model", None))
            parsed = _parse_json(response.content or "")
        except Exception as e:
            logger.warning("Help request: LLM unavailable, using a plain request: %s", e)
            return fallback
        request = {k: str(parsed.get(k) or fallback[k]) for k in ("tried", "stuck_on", "need")}
        return {**request, **voice_fields(parsed)}


class ApplyHelpResponseAction(TaskAction):
    """Route on the human's answer to a help request: retry, redirect or abandon.

    - ``retry``: guidance is recorded in ``__help_history__`` and the same
      workflow re-runs with it appended to the goal.
    - ``redirect``: ``goal`` becomes the human's text (``original_goal`` keeps
      the first one) and the loop goes back to the ethics input gate. An empty
      redirect is treated as a retry.
    - ``abandon``: the failure is kept, noted as abandoned, and recorded as usual.
    """

    description = "Apply a human's answer to an 'I'm stuck' help request."
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(
            name="response_task_id",
            type="string",
            description="Task definition id of the help-request human task",
            required=False,
            default="stuck_help_request",
        ),
        ParameterDef(
            name="result_key",
            type="string",
            description="Process property holding the goal workflow's result",
            required=False,
            default="execution_result",
        ),
    ]

    outputs = [
        ParameterDef(
            name="decision",
            type="string",
            description="retry | redirect | abandon",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        response_task_id = task.properties.get("response_task_id", "stuck_help_request")
        result_key = task.properties.get("result_key", "execution_result")
        answer = context.get_task_output(response_task_id) or {}
        decision = str(answer.get("decision", "abandon")).strip().lower()
        if decision not in DECISIONS:
            decision = "abandon"
        guidance = str(answer.get("guidance") or "").strip()[:_MAX_GUIDANCE_CHARS]
        if decision == "redirect" and not guidance:
            decision = "retry"

        result = dict(context.get_process_property(result_key) or {})
        goal = context.get_process_property("goal", "")
        # Clipped: the history is replayed into every later child goal.
        error = str(result.get("error") or "unknown error")[:_MAX_ERROR_CHARS]
        entry = {"error": error, "decision": decision, "guidance": guidance}

        if decision == "redirect":
            entry["previous_goal"] = goal
            if context.get_process_property("original_goal") is None:
                context.set_process_property("original_goal", goal)
            context.set_process_property("goal", guidance)
        elif decision == "abandon":
            error = result.get("error") or "Workflow execution failed"
            result["error"] = error + ABANDONED_SUFFIX
            context.set_process_property(result_key, result)

        history = list(context.get_process_property(HELP_HISTORY_KEY) or [])
        context.set_process_property(HELP_HISTORY_KEY, history + [entry])
        logger.info("Help response: %s", decision)
        return TaskResult(success=True, output=entry, next_route=decision)


def _parse_json(content: str) -> dict[str, Any]:
    """Parse a JSON object, tolerating a fenced code block."""
    if "```" in content:
        start = content.index("```") + 3
        if content[start:].startswith("json"):
            start += 4
        content = content[start : content.index("```", start)]
    parsed = json.loads(content.strip())
    if not isinstance(parsed, dict):
        raise ValueError("help request is not a JSON object")
    return parsed


def _track_cost(context: ExecutionContext, response: Any, model: str | None) -> None:
    """Add the help request's tokens and cost to the process totals."""
    from zebra_tasks.llm.pricing import usage_cost

    usage = response.usage
    tokens = context.get_process_property("__total_tokens__", 0)
    context.set_process_property("__total_tokens__", tokens + usage.total_tokens)
    cost = usage_cost(model or response.model, usage)
    total = context.get_process_property("__total_cost__", 0.0)
    context.set_process_property("__total_cost__", total + cost)
