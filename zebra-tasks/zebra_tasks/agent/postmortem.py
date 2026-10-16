"""Postmortem journal: learn a lesson from an incident into long-term memory (#175).

``write_postmortem`` runs after a goal fails (in the Agent Main Loop), after a goal
times out or crashes, and after the user rates a run 1 or 2 (both via the
*Postmortem* system workflow). A cheap model writes what happened, the root cause
and the lesson; it is stored as a ``PostmortemEntry`` in the ``MemoryStore``.
``consult_memory`` recalls the lessons relevant to later goals, and
:func:`with_lessons` appends them to the goal the executed workflow sees.
"""

import logging
from typing import Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction
from zebra_agent.memory import POSTMORTEM_TRIGGERS, PostmortemEntry

from zebra_tasks.agent.stuck import _as_bool, _parse_json, _task_lines, _track_cost
from zebra_tasks.agent.voice import VOICE_SCHEMA_FIELDS, voice_fields
from zebra_tasks.llm.base import Message
from zebra_tasks.llm.providers import get_provider

logger = logging.getLogger(__name__)

# Where consult_memory keeps its result; with_lessons reads the lessons from it.
MEMORY_SHORTLIST_KEY = "memory_shortlist"

_MAX_GOAL_CHARS = 1000
_MAX_ERROR_CHARS = 1000
_MAX_FEEDBACK_CHARS = 1000

SYSTEM_PROMPT = (
    """\
You are Zebra, an AI agent, writing a short postmortem about one of your own runs that
went wrong, so you don't repeat the mistake. Be blameless and concrete.

- what_happened: what you attempted and how it went wrong, one or two sentences
- root_cause: the most likely underlying cause, not just the symptom, one or two sentences
- lesson: one actionable rule for next time on a similar goal, written so it can be
  followed without this context ("When ..., do ... instead of ..."). If the cause was
  outside your control (an outage, a missing credential), say what to check first.

Do not invent details that are not in the evidence.

Respond with JSON only:
{
    "what_happened": "...",
    "root_cause": "...",
    "lesson": "...",
"""
    + VOICE_SCHEMA_FIELDS
    + """
}"""
)

USER_PROMPT = """\
Why this postmortem: {reason}
Goal: {goal}
Workflow used: {workflow_name}
Error: {error}
{feedback}Steps that ran:
{tasks}"""

_REASONS = {
    "failure": "the goal workflow failed",
    "timeout": "the goal was stopped before it finished (timed out or crashed)",
    "low_rating": "the user rated the result {rating}/5",
}


def with_lessons(goal: str, properties: dict[str, Any]) -> str:
    """Return the goal followed by lessons from past incidents, when any were recalled.

    Used when spawning the executed goal workflow, which only sees ``goal``.

    Args:
        goal: The (possibly already annotated) goal.
        properties: Process properties, checked for ``memory_shortlist.lessons_context``.

    Returns:
        The goal unchanged when no lessons were recalled; otherwise the goal
        followed by a delimited ``<lessons>`` section.
    """
    shortlist = properties.get(MEMORY_SHORTLIST_KEY)
    if not isinstance(shortlist, dict) or not shortlist.get("lessons_context"):
        return goal
    return (
        f"{goal}\n\nLessons I learned from past incidents on similar goals; "
        "apply them where they fit.\n"
        f"<lessons>\n{shortlist['lessons_context']}\n</lessons>"
    )


def _user_id(context: ExecutionContext) -> int | None:
    """The goal submitter's id from ``__user_id__`` (#151), or None."""
    try:
        value = context.get_process_property("__user_id__")
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


class WritePostmortemAction(TaskAction):
    """Write and store a postmortem for a failed, timed-out or badly rated run.

    Skips (stores nothing) when the trigger is ``failure`` and the run succeeded,
    when there is no memory store, when the run already has a postmortem, or when
    no LLM is available: a lesson without a root cause is noise. Never fails.
    """

    description = "Write a postmortem (what happened, root cause, lesson) into long-term memory."
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(name="goal", type="string", description="The run's goal", required=True),
        ParameterDef(
            name="workflow_name",
            type="string",
            description="The goal workflow that ran",
            required=False,
            default="",
        ),
        ParameterDef(
            name="trigger",
            type="string",
            description="failure | timeout | low_rating",
            required=False,
            default="failure",
        ),
        ParameterDef(
            name="success",
            type="bool",
            description="Whether the goal workflow succeeded (failure trigger skips on success)",
            required=False,
            default=False,
        ),
        ParameterDef(
            name="error", type="string", description="The run's error", required=False, default=""
        ),
        ParameterDef(
            name="run_id",
            type="string",
            description="The run this postmortem is about (default: process run_id)",
            required=False,
        ),
        ParameterDef(
            name="rating", type="int", description="User rating (low_rating)", required=False
        ),
        ParameterDef(
            name="user_feedback",
            type="string",
            description="The user's feedback on the run",
            required=False,
            default="",
        ),
        ParameterDef(
            name="model",
            type="string",
            description="LLM model for the postmortem (default haiku)",
            required=False,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key for the postmortem",
            required=False,
            default="postmortem",
        ),
    ]

    outputs = [
        ParameterDef(
            name="written",
            type="bool",
            description="True when a postmortem was stored",
            required=True,
        ),
        ParameterDef(
            name="lesson", type="string", description="The lesson learned", required=False
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        props = task.properties
        output_key = props.get("output_key", "postmortem")

        def _text(name: str) -> str:
            value = context.resolve_template(str(props.get(name) or ""))
            return "" if value == "None" else value

        trigger = _text("trigger") or "failure"
        if trigger not in POSTMORTEM_TRIGGERS:
            logger.warning("Postmortem: unknown trigger %r, using 'failure'", trigger)
            trigger = "failure"

        if trigger == "failure" and _as_bool(_text("success")):
            return self._skip(context, output_key, "run succeeded")

        memory = context.extras.get("__memory_store__")
        if memory is None:
            logger.warning("Postmortem: no memory store, not writing one")
            return self._skip(context, output_key, "no memory store")

        run_id = _text("run_id") or str(context.get_process_property("run_id") or "")
        try:
            if run_id and await memory.get_postmortem_by_run_id(run_id) is not None:
                return self._skip(context, output_key, "run already has a postmortem")
        except Exception as e:  # noqa: BLE001 - a postmortem must never fail the goal
            logger.warning("Postmortem: lookup failed, not writing one: %s", e)
            return self._skip(context, output_key, "memory store unavailable")

        goal = _text("goal")
        workflow_name = _text("workflow_name")
        error = _text("error")
        parsed = await self._write(task, context, trigger, goal, workflow_name, error)
        if parsed is None:
            return self._skip(context, output_key, "no LLM available")

        entry = PostmortemEntry.create(
            run_id=run_id,
            goal=goal,
            workflow_name=workflow_name,
            trigger=trigger,
            what_happened=parsed["what_happened"],
            root_cause=parsed["root_cause"],
            lesson=parsed["lesson"],
            voice=parsed.get("voice"),
            confidence=parsed.get("confidence"),
            user_id=_user_id(context),
        )
        try:
            await memory.add_postmortem(entry)
        except Exception as e:  # noqa: BLE001
            logger.warning("Postmortem: could not store it: %s", e)
            return self._skip(context, output_key, "memory store unavailable")

        result = {
            "written": True,
            "id": entry.id,
            "trigger": trigger,
            "what_happened": entry.what_happened,
            "root_cause": entry.root_cause,
            "lesson": entry.lesson,
            "voice": entry.voice,
            "confidence": entry.confidence,
        }
        context.set_process_property(output_key, result)
        logger.info("Postmortem (%s) stored for run %s: %s", trigger, run_id, entry.lesson[:120])
        return TaskResult.ok(output=result)

    @staticmethod
    def _skip(context: ExecutionContext, output_key: str, reason: str) -> TaskResult:
        result = {"written": False, "reason": reason}
        context.set_process_property(output_key, result)
        return TaskResult.ok(output=result)

    async def _write(
        self,
        task: TaskInstance,
        context: ExecutionContext,
        trigger: str,
        goal: str,
        workflow_name: str,
        error: str,
    ) -> dict[str, Any] | None:
        """Ask a cheap model for the postmortem; None when it cannot be written."""
        props = task.properties
        rating = context.resolve_template(str(props.get("rating") or "?"))
        feedback = context.resolve_template(str(props.get("user_feedback") or ""))
        feedback_line = (
            f"User feedback: {feedback[:_MAX_FEEDBACK_CHARS]}\n"
            if feedback and feedback != "None"
            else ""
        )
        provider_name = context.get_process_property("__llm_provider_name__") or "anthropic"
        # A cheap model: a short reflection, not the goal's work.
        model = props.get("model") or "haiku"
        try:
            provider = get_provider(provider_name, model)
            response = await provider.complete(
                messages=[
                    Message.system(SYSTEM_PROMPT),
                    Message.user(
                        USER_PROMPT.format(
                            reason=_REASONS[trigger].format(rating=rating),
                            goal=goal[:_MAX_GOAL_CHARS],
                            workflow_name=workflow_name or "unknown",
                            error=(error or "none recorded")[:_MAX_ERROR_CHARS],
                            feedback=feedback_line,
                            tasks=_task_lines(
                                context.get_process_property("__task_executions__", [])
                            ),
                        )
                    ),
                ],
                temperature=0.3,
                max_tokens=600,
            )
            _track_cost(context, response, getattr(provider, "model", None))
            parsed = _parse_json(response.content or "")
        except Exception as e:  # noqa: BLE001
            logger.warning("Postmortem: LLM unavailable, not writing one: %s", e)
            return None

        fields = {k: str(parsed.get(k) or "").strip() for k in ("what_happened", "root_cause")}
        lesson = str(parsed.get("lesson") or "").strip()
        if not lesson:
            logger.warning("Postmortem: the model gave no lesson, not storing one")
            return None
        return {**fields, "lesson": lesson, **voice_fields(parsed)}
