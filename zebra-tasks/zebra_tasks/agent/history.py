"""Workflow history actions (F138).

``assess_history_need`` decides whether a goal needs past workflow runs and
extracts the filters; ``get_workflow_history`` fetches matching runs from the
``MetricsStore`` (``__metrics_store__`` in ``context.extras``) and renders a
size-bounded ``history_context`` string for downstream LLM steps.
"""

import json
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.agent.followup import CONTINUATION_COMMENT_KEY, PREVIOUS_RUN_CONTEXT_KEY
from zebra_tasks.llm.base import Message
from zebra_tasks.llm.providers import get_provider

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 20
MAX_FIELD_CHARS = 300
MAX_CONTEXT_CHARS = 4000
_MAX_GOAL_LEN = 500
WORKFLOW_HISTORY_KEY = "workflow_history"

_RELATIVE_RE = re.compile(r"^([+-]?)(\d+)\s*([mhdw])$", re.IGNORECASE)
_UNITS = {"m": "minutes", "h": "hours", "d": "days", "w": "weeks"}

# Cheap pre-check: only goals mentioning the past pay for an LLM call.
_HISTORY_CUES = re.compile(
    r"\b(last (week|month|year|time|night)|yesterday|earlier|before|previous(ly)?|"
    r"history|ago|since|recent(ly)?|past|did i|have we|have i|did we|did you|"
    r"we (tried|discussed|did)|i asked|you (said|told|found|did)|again|remind me|"
    r"continu(e|es|ing)|carry on|pick up|where (were|was) we|what next|next steps?|"
    r"follow[- ]?up|our .{0,40}\bplans?|"
    r"january|february|march|april|june|july|august|september|october|"
    r"november|december|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.IGNORECASE,
)


def parse_time(value: Any, now: datetime | None = None) -> datetime | None:
    """Parse an ISO-8601 timestamp or relative offset into a UTC datetime.

    Relative offsets are ``<n><unit>`` with unit ``m``/``h``/``d``/``w``. An
    unsigned or ``-`` offset is in the past (``7d`` == ``-7d``); ``+`` is future.

    Args:
        value: ISO string, relative offset, datetime, or empty/None.
        now: Reference time for relative offsets (defaults to current UTC).

    Returns:
        A timezone-aware UTC datetime, or None for empty input.

    Raises:
        ValueError: If the value is neither ISO-8601 nor a relative offset.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value).strip()
    if not text or text.lower() == "none":
        return None
    match = _RELATIVE_RE.match(text)
    if match:
        sign, amount, unit = match.groups()
        delta = timedelta(**{_UNITS[unit.lower()]: int(amount)})
        base = now or datetime.now(UTC)
        return base + delta if sign == "+" else base - delta
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError(f"Invalid time value {text!r}: use ISO-8601 or e.g. -7d, 24h") from e
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _clip(value: Any, limit: int = MAX_FIELD_CHARS) -> str | None:
    if value is None or value == "":
        return None
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return None if not text or text.lower() == "none" else text


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool) or value is None:
        return value
    text = str(value).strip().lower()
    if text in ("true", "yes", "1"):
        return True
    if text in ("false", "no", "0"):
        return False
    return None


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _resolve(task: TaskInstance, context: ExecutionContext, key: str) -> Any:
    value = task.properties.get(key)
    if isinstance(value, str) and "{{" in value:
        value = context.resolve_template(value)
    return value


def _compact_run(run: Any) -> dict[str, Any]:
    started = run.started_at.isoformat() if run.started_at else None
    return {
        "id": run.id,
        "workflow_name": run.workflow_name,
        "goal": _clip(run.goal),
        "started_at": started,
        "success": run.success,
        "user_rating": run.user_rating,
        "output": _clip(run.output),
        "error": _clip(run.error),
    }


def format_history_context(runs: list[dict[str, Any]], filters: dict[str, Any]) -> str:
    """Render runs as an LLM-ready summary capped at MAX_CONTEXT_CHARS."""
    shown = ", ".join(f"{k}={v}" for k, v in filters.items() if v is not None) or "none"
    header = f"Workflow history search (filters: {shown})"
    if not runs:
        return f"{header}\nNo matching workflow history found."
    lines = [f"{header} — {len(runs)} run(s), newest first:"]
    used = len(lines[0])
    for i, run in enumerate(runs):
        status = "succeeded" if run["success"] else "failed"
        rating = f", rated {run['user_rating']}/5" if run["user_rating"] else ""
        entry = f"- [{run['started_at']}] {run['workflow_name']} ({status}{rating}): {run['goal']}"
        if run["output"]:
            entry += f"\n  Result: {run['output']}"
        if run["error"]:
            entry += f"\n  Error: {run['error']}"
        if used + len(entry) + 1 > MAX_CONTEXT_CHARS:
            lines.append(f"… {len(runs) - i} more run(s) omitted")
            break
        lines.append(entry)
        used += len(entry) + 1
    return "\n".join(lines)


class GetWorkflowHistoryAction(TaskAction):
    """Fetch past workflow runs filtered by time window and text.

    Reads ``__metrics_store__`` from ``context.extras``; degrades to empty
    history when absent. Results are scoped to the goal's owner
    (``__user_id__``) and exclude the current run (``run_id``).

    Example workflow usage::

        tasks:
          get_history:
            name: "Get Workflow History"
            action: get_workflow_history
            properties:
              since: "-7d"
              text: "pension"
              output_key: workflow_history
    """

    description = "Fetch past workflow runs filtered by date/time window and search text."
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(
            name="since",
            type="string",
            description="Start (inclusive): ISO-8601 or relative offset like -7d, 24h",
            required=False,
        ),
        ParameterDef(
            name="until",
            type="string",
            description="End (exclusive): ISO-8601 or relative offset",
            required=False,
        ),
        ParameterDef(
            name="text",
            type="string",
            description="Case-insensitive text to match in past goals",
            required=False,
        ),
        ParameterDef(
            name="workflow_name",
            type="string",
            description="Only runs of this workflow",
            required=False,
        ),
        ParameterDef(
            name="success",
            type="bool",
            description="Only successful (true) or failed (false) runs",
            required=False,
        ),
        ParameterDef(
            name="limit",
            type="int",
            description="Maximum runs to return (store caps at 200)",
            required=False,
            default=DEFAULT_LIMIT,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the result",
            required=False,
            default=WORKFLOW_HISTORY_KEY,
        ),
    ]

    outputs = [
        ParameterDef(name="runs", type="list", description="Compact run records", required=True),
        ParameterDef(name="count", type="int", description="Number of runs", required=True),
        ParameterDef(name="filters", type="dict", description="Resolved filters", required=True),
        ParameterDef(
            name="history_context",
            type="string",
            description="Size-bounded LLM-ready summary of the runs",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Search the metrics store and store the compact result."""
        output_key = task.properties.get("output_key", WORKFLOW_HISTORY_KEY)
        try:
            since = parse_time(_resolve(task, context, "since"))
            until = parse_time(_resolve(task, context, "until"))
        except ValueError as e:
            return TaskResult.fail(str(e))

        try:
            limit = int(_resolve(task, context, "limit") or DEFAULT_LIMIT)
        except (TypeError, ValueError):
            limit = DEFAULT_LIMIT

        filters = {
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
            "text": _optional_str(_resolve(task, context, "text")),
            "workflow_name": _optional_str(_resolve(task, context, "workflow_name")),
            "success": _optional_bool(_resolve(task, context, "success")),
            "limit": limit,
        }

        store = context.extras.get("__metrics_store__")
        runs: list[dict[str, Any]] = []
        if store is None:
            logger.warning("get_workflow_history: no metrics store; returning empty history")
        else:
            user_id = _optional_int(context.get_process_property("__user_id__"))
            current_run = context.get_process_property("run_id")
            # Fetch one extra so excluding the current run still fills the limit.
            found = await store.search_runs(
                since=since,
                until=until,
                text=filters["text"],
                workflow_name=filters["workflow_name"],
                success=filters["success"],
                limit=limit + 1,
                user_id=user_id,
            )
            runs = [_compact_run(r) for r in found if r.id != current_run][:limit]

        result = {
            "runs": runs,
            "count": len(runs),
            "filters": filters,
            "history_context": format_history_context(runs, filters),
        }
        context.set_process_property(output_key, result)
        logger.info("get_workflow_history: %d run(s) for filters %s", len(runs), filters)
        return TaskResult.ok(output=result)


SYSTEM_PROMPT = """\
You decide whether answering a user's goal requires looking up the AI agent's own
past workflow runs (previous goals it worked on and their results).

History is needed when the goal refers to earlier interactions or past work, e.g.
"what did I ask you about X last week?", "have we tried this before?", "continue the
research you did on Y", "summarise what you did yesterday". It is NOT needed for
goals that merely mention dates or the past as subject matter ("history of Rome").

Today is {today} (UTC). When history is needed, extract filters:
- since / until: ISO-8601 UTC timestamps or relative offsets like "-7d", "-24h";
  null when the goal gives no time bound.
- text: 1-3 keywords most likely to appear in the earlier goal; null for "everything".
  Keywords are matched individually against past goals, so use the topic nouns
  (e.g. "holiday Scotland"), not the wording of the current request.
A goal that continues a previous run, or a user comment such as "check workflow
history", usually needs history: the earlier work on the same topic may predate
the previous run.

Respond with JSON only:
{{"needs_history": true|false, "since": ..., "until": ..., "text": ..., "reasoning": "..."}}"""


class AssessHistoryNeedAction(TaskAction):
    """Decide whether a goal needs past workflow history and extract filters.

    Goals with no history cues route ``no_history`` without an LLM call.
    Otherwise a cheap (haiku) call decides and extracts ``since``/``until``/
    ``text``. LLM errors degrade to ``no_history`` rather than failing.

    Routes:
        needs_history: fetch history (e.g. via ``get_workflow_history``)
        no_history: skip the fetch
    """

    description = "Decide whether a goal needs past workflow history; extract date/text filters."
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(name="goal", type="string", description="The user's goal", required=True),
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
            description="LLM model (defaults to haiku — this is a cheap classifier)",
            required=False,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the decision",
            required=False,
            default="history_need",
        ),
    ]

    outputs = [
        ParameterDef(
            name="needs_history", type="bool", description="Whether to fetch", required=True
        ),
        ParameterDef(name="since", type="string", description="Start filter", required=False),
        ParameterDef(name="until", type="string", description="End filter", required=False),
        ParameterDef(name="text", type="string", description="Search text", required=False),
        ParameterDef(name="reasoning", type="string", description="Why", required=False),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Classify the goal and route needs_history / no_history."""
        goal = _resolve(task, context, "goal") or ""
        output_key = task.properties.get("output_key", "history_need")
        # F150: a continuation is about past work by definition; its comment and
        # previous goal often carry the cue ("check workflow history") and topic.
        previous = context.process.properties.get(PREVIOUS_RUN_CONTEXT_KEY)
        is_continuation = isinstance(previous, dict)
        comment = context.process.properties.get(CONTINUATION_COMMENT_KEY) or ""
        query = f"Goal: {goal[:_MAX_GOAL_LEN]}"
        if is_continuation:
            previous_goal = str(previous.get("goal") or "")[:_MAX_GOAL_LEN]
            query += f"\nContinues a previous run whose goal was: {previous_goal}"
        if comment:
            query += f"\nUser's comment: {str(comment)[:_MAX_GOAL_LEN]}"

        if not is_continuation and not _HISTORY_CUES.search(f"{goal}\n{comment}"):
            return self._finish(context, output_key, False, "No history cues in goal")

        provider_name = (
            task.properties.get("provider")
            or context.process.properties.get("__llm_provider_name__")
            or "anthropic"
        )
        model = task.properties.get("model") or "haiku"
        try:
            provider = get_provider(provider_name, model)
            response = await provider.complete(
                messages=[
                    Message.system(SYSTEM_PROMPT.format(today=datetime.now(UTC).date())),
                    Message.user(query),
                ],
                temperature=0.0,
                max_tokens=300,
            )
            parsed = json.loads(_strip_fences(response.content or ""))
        except Exception as e:
            logger.warning("assess_history_need: LLM decision failed, skipping history: %s", e)
            return self._finish(context, output_key, False, f"Decision unavailable: {e}")

        if not parsed.get("needs_history"):
            return self._finish(context, output_key, False, parsed.get("reasoning", ""))

        # Validate time filters here so a bad extraction can't fail the fetch.
        filters = {}
        for key in ("since", "until"):
            try:
                parsed_time = parse_time(parsed.get(key))
            except ValueError:
                logger.warning("assess_history_need: ignoring bad %s %r", key, parsed.get(key))
                parsed_time = None
            filters[key] = parsed_time.isoformat() if parsed_time else None
        filters["text"] = _optional_str(parsed.get("text"))
        return self._finish(context, output_key, True, parsed.get("reasoning", ""), **filters)

    @staticmethod
    def _finish(
        context: ExecutionContext,
        output_key: str,
        needs: bool,
        reasoning: str,
        since: str | None = None,
        until: str | None = None,
        text: str | None = None,
    ) -> TaskResult:
        result = {
            "needs_history": needs,
            "since": since,
            "until": until,
            "text": text,
            "reasoning": reasoning,
        }
        context.set_process_property(output_key, result)
        route = "needs_history" if needs else "no_history"
        return TaskResult(success=True, output=result, next_route=route)


def _strip_fences(content: str) -> str:
    """Strip a ```json fenced block if the model wrapped its JSON."""
    match = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
    return match.group(1).strip() if match else content.strip()


def with_workflow_history(goal: str, properties: dict[str, Any]) -> str:
    """Return the goal followed by fetched workflow history, when present.

    Used when spawning the executed goal workflow, which only sees ``goal``.

    Args:
        goal: The (possibly already annotated) goal.
        properties: Process properties, checked for ``workflow_history``.

    Returns:
        The goal unchanged when no history was fetched; otherwise the goal
        followed by a delimited ``<workflow_history>`` section.
    """
    history = properties.get(WORKFLOW_HISTORY_KEY)
    if not isinstance(history, dict) or not history.get("history_context"):
        return goal
    return (
        f"{goal}\n\nRelevant past workflow runs were retrieved for this goal; "
        "use them where helpful.\n"
        f"<workflow_history>\n{history['history_context']}\n</workflow_history>"
    )
