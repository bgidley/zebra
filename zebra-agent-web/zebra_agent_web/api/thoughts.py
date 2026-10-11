"""Zebra's recorded reasoning, as "thoughts" for the web UI voice layer (#161).

Reads only what a run already recorded on its Agent Main Loop process: the
ethics gates, continuation assessment, workflow choice, planning concerns and
post-run ethics review. Nothing here calls an LLM or invents text.

A thought's text is Zebra's first-person ``voice`` line when the step recorded
one, otherwise the step's own recorded reasoning (``is_voice`` is False then).
``confidence`` is only set when Zebra recorded one; the UI shows a certainty
stripe only in that case.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from asgiref.sync import sync_to_async
from django.db.models import Q

logger = logging.getLogger(__name__)

NOT_CONTINUATION = "not_continuation"


@dataclass(frozen=True)
class Thought:
    """One piece of recorded reasoning from a run."""

    kind: str
    label: str
    task_id: str
    text: str
    is_voice: bool
    confidence: float | None
    quiet: bool = False


@dataclass(frozen=True)
class FeedThought:
    """A thought placed in the home feed, with the run it came from."""

    thought: Thought
    goal: str
    run_id: str | None
    at: datetime | None


def _text(value: Any) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _confidence(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return min(1.0, max(0.0, float(value)))


def _thought(
    kind: str, label: str, task_id: str, data: dict, fallback: str, quiet: bool
) -> Thought | None:
    voice = _text(data.get("voice"))
    text = voice or _text(fallback)
    if not text:
        return None
    return Thought(
        kind=kind,
        label=label,
        task_id=task_id,
        text=text,
        is_voice=bool(voice),
        confidence=_confidence(data.get("confidence")),
        # A voice line is never quiet: Zebra chose to say something.
        quiet=quiet and not voice,
    )


def _ethics(kind: str, label: str, task_id: str, data: dict) -> Thought | None:
    concerns = [c for c in data.get("concerns") or [] if c]
    verdict = data.get("approved", data.get("ethical"))
    quiet = verdict is True and not concerns
    return _thought(kind, label, task_id, data, data.get("overall_reasoning"), quiet)


def _continuation(data: dict) -> Thought | None:
    if data.get("decision") in (None, NOT_CONTINUATION):
        return None
    return _thought(
        "continuation", "Continuation", "assess_continuation", data, data.get("rationale"), False
    )


def _selection(data: dict) -> Thought | None:
    reasoning = data.get("reasoning")
    name = data.get("workflow_name") or data.get("suggested_name")
    if not _text(data.get("voice")) and name and _text(reasoning):
        reasoning = f"{name}: {_text(reasoning)}"
    return _thought("selection", "Workflow choice", "select_workflow", data, reasoning, False)


def _concerns(data: dict) -> Thought | None:
    concerns = [c for c in data.get("concerns") or [] if c]
    return _thought(
        "concerns",
        "Planning concerns",
        "flag_concerns",
        data,
        data.get("summary"),
        quiet=not concerns,
    )


# (process property, builder) in the order the Agent Main Loop runs them.
_SOURCES = (
    (
        "ethics_input_assessment",
        lambda d: _ethics("ethics_input", "Ethics, input", "ethics_input_gate", d),
    ),
    ("continuation_assessment", _continuation),
    ("selection", _selection),
    ("planning_concerns", _concerns),
    (
        "ethics_plan_assessment",
        lambda d: _ethics("ethics_plan", "Ethics, plan", "ethics_plan_review", d),
    ),
    (
        "ethics_post_assessment",
        lambda d: _ethics("ethics_post", "Ethics, after the run", "ethics_post_review", d),
    ),
)


def thoughts_for_process(properties: dict | None) -> list[Thought]:
    """Return the run's recorded reasoning in the order the steps ran.

    Args:
        properties: The Agent Main Loop (root) process properties.

    Returns:
        Thoughts for every reasoning step that recorded something. Malformed
        entries are skipped rather than raising.
    """
    thoughts: list[Thought] = []
    for key, build in _SOURCES:
        data = (properties or {}).get(key)
        if not isinstance(data, dict):
            continue
        try:
            thought = build(data)
        except Exception:  # never let one odd record break a page
            logger.warning("Could not read thought from %s", key, exc_info=True)
            continue
        # The continuation assessor also writes ``selection`` with its own rationale;
        # don't say the same thing twice.
        if thought is not None and not any(_same(thought, t) for t in thoughts):
            thoughts.append(thought)
    return thoughts


def _same(a: Thought, b: Thought) -> bool:
    return a.text == b.text or a.text.endswith(": " + b.text)


@sync_to_async(thread_sensitive=False)
def _recent_root_process_rows(limit: int, user_id: int | None) -> list[tuple]:
    from zebra_agent_web.api.models import ProcessInstanceModel

    queryset = ProcessInstanceModel.objects.filter(
        Q(parent_process_id__isnull=True) | Q(parent_process_id="")
    )
    if user_id is not None:
        queryset = queryset.filter(user_id=user_id)
    return list(queryset.order_by("-updated_at").values_list("properties", "updated_at")[:limit])


async def recent_thoughts(limit: int = 6, scan: int = 25) -> list[FeedThought]:
    """Zebra's most recent notable thoughts across recent runs, newest run first.

    Scans the ``scan`` most recently updated top-level processes for the current
    user and keeps non-quiet thoughts, latest step first within each run.

    Args:
        limit: Maximum thoughts to return.
        scan: How many recent root processes to look at.
    """
    from zebra_agent_web.middleware import get_current_user_id

    rows = await _recent_root_process_rows(scan, get_current_user_id())
    feed: list[FeedThought] = []
    for raw, updated_at in rows:
        try:
            properties = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except (TypeError, ValueError):
            continue
        goal = _text(properties.get("goal"))
        for thought in reversed(thoughts_for_process(properties)):
            if thought.quiet:
                continue
            feed.append(
                FeedThought(
                    thought=thought,
                    goal=goal,
                    run_id=properties.get("run_id"),
                    at=updated_at,
                )
            )
            if len(feed) >= limit:
                return feed
    return feed
