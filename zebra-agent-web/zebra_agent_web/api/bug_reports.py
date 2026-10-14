"""Bug reports from the web UI's "Report a bug" button (#186).

A report is a "Bug Report" process (``zebra-agent/workflows/bug_report.yaml``).
This module turns a submitted form into that process's properties — the
user's view, the technical view (browser + server) and a markdown summary
for the reviewer — and summarises recent reports for the ``/bugs/`` page.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from django.urls import Resolver404, resolve

from zebra_agent_web.api.models import (
    ProcessDefinitionModel,
    ProcessInstanceModel,
    TaskInstanceModel,
)
from zebra_agent_web.api.version import _VERSION

logger = logging.getLogger(__name__)

BUG_REPORT_WORKFLOW = "Bug Report"
REVIEW_TASK = "review"

SEVERITIES = {
    "blocker": "Blocks me",
    "major": "Gets in the way",
    "minor": "Minor annoyance",
    "cosmetic": "Cosmetic",
}
DEFAULT_SEVERITY = "minor"

# Must match the review task's verdict enum in bug_report.yaml
VERDICTS = {
    "confirmed": "Confirmed",
    "needs_info": "Needs more info",
    "duplicate": "Duplicate",
    "not_a_bug": "Not a bug",
    "fixed": "Already fixed",
}

TITLE_MAX = 200
TEXT_MAX = 10_000
CLIENT_CONTEXT_MAX_BYTES = 64 * 1024

# URL kwargs that point at something whose state is worth recording
_PROCESS_KWARGS = ("process_id",)
_TASK_KWARGS = ("task_id",)
_RUN_KWARGS = ("run_id",)


class BugReportError(ValueError):
    """The submitted report is missing a required field."""


def parse_user_report(data: dict[str, Any]) -> dict[str, str]:
    """Validate and trim the user's view of the bug.

    Args:
        data: Form fields (``title``, ``description``, ``expected``, ``steps``,
            ``severity``).

    Returns:
        The cleaned report.

    Raises:
        BugReportError: If the title or description is blank.
    """

    def _text(key: str, limit: int) -> str:
        return str(data.get(key) or "").strip()[:limit]

    report = {
        "title": _text("title", TITLE_MAX),
        "description": _text("description", TEXT_MAX),
        "expected": _text("expected", TEXT_MAX),
        "steps": _text("steps", TEXT_MAX),
        "severity": str(data.get("severity") or "").strip(),
    }
    if not report["title"]:
        raise BugReportError("A title is required")
    if not report["description"]:
        raise BugReportError("Please describe what happened")
    if report["severity"] not in SEVERITIES:
        report["severity"] = DEFAULT_SEVERITY
    return report


def parse_client_context(raw: str | None) -> dict[str, Any]:
    """Parse the browser's technical context, never failing.

    The browser posts it as a JSON string. Anything missing, oversized or not
    a JSON object is replaced by a note so the report is still recorded.
    """
    if not raw:
        return {"note": "No client context was sent"}
    if len(raw.encode()) > CLIENT_CONTEXT_MAX_BYTES:
        return {"note": f"Client context dropped: over {CLIENT_CONTEXT_MAX_BYTES} bytes"}
    try:
        context = json.loads(raw)
    except json.JSONDecodeError:
        return {"note": "Client context dropped: not valid JSON"}
    if not isinstance(context, dict):
        return {"note": "Client context dropped: not a JSON object"}
    return context


def resolve_page(page_url: str | None) -> dict[str, Any] | None:
    """Resolve the reported page's path to a view name and URL arguments."""
    if not page_url:
        return None
    path = urlparse(page_url).path or "/"
    try:
        match = resolve(path)
    except Resolver404:
        return {"path": path, "view": None, "kwargs": {}}
    return {"path": path, "view": match.view_name, "kwargs": dict(match.kwargs)}


async def linked_state(route: dict[str, Any] | None, store, metrics) -> dict[str, Any] | None:
    """Record the state of the process, task or run the reported page showed.

    Best effort: a lookup failure becomes a note rather than an error.
    """
    if not route:
        return None
    kwargs = route.get("kwargs") or {}
    try:
        for key in _TASK_KWARGS:
            if kwargs.get(key):
                task = await store.load_task(kwargs[key])
                if task is None:
                    return {"task_id": kwargs[key], "note": "Task not found"}
                linked = await _process_state(store, task.process_id)
                linked.update(
                    task_id=task.id,
                    task_definition_id=task.task_definition_id,
                    task_state=task.state.value,
                )
                return linked
        for key in _PROCESS_KWARGS:
            if kwargs.get(key):
                return await _process_state(store, kwargs[key])
        for key in _RUN_KWARGS:
            if kwargs.get(key) and metrics is not None:
                run = await metrics.get_run(kwargs[key])
                if run is None:
                    return {"run_id": kwargs[key], "note": "Run not found in metrics"}
                return {
                    "run_id": run.id,
                    "workflow_name": run.workflow_name,
                    "success": run.success,
                    "error": run.error,
                    "started_at": run.started_at.isoformat() if run.started_at else None,
                    "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                }
    except Exception as e:
        logger.warning("Bug report: could not load linked state for %s", route, exc_info=True)
        return {"note": f"Linked state lookup failed: {e}"}
    return None


async def _process_state(store, process_id: str) -> dict[str, Any]:
    process = await store.load_process(process_id)
    if process is None:
        return {"process_id": process_id, "note": "Process not found"}
    definition = await store.load_definition(process.definition_id)
    props = process.properties or {}
    return {
        "process_id": process.id,
        "workflow_name": definition.name if definition else process.definition_id,
        "process_state": process.state.value,
        "parent_process_id": process.parent_process_id,
        "error": props.get("__error__"),
        "failed_task": props.get("__failed_task__"),
    }


def server_context(request, route: dict[str, Any] | None) -> dict[str, Any]:
    """What the server knows at submission time."""
    user = getattr(request, "user", None)
    return {
        "received_at": datetime.now(UTC).isoformat(),
        "version": {
            "short_hash": _VERSION.get("short_hash", "unknown"),
            "date": _VERSION.get("date", ""),
        },
        "user": {
            "id": getattr(user, "id", None),
            "username": getattr(user, "username", None),
        },
        "user_agent": request.headers.get("User-Agent", ""),
        "referer": request.headers.get("Referer", ""),
        "route": route,
    }


def build_properties(
    report: dict[str, str], technical: dict[str, Any], user_id: int | None
) -> dict[str, Any]:
    """Process properties for a new Bug Report process."""
    return {
        "goal": f"Bug report: {report['title']}",
        "bug_title": report["title"],
        "bug_report": report,
        "technical_context": technical,
        "bug_report_markdown": render_markdown(report, technical),
        "user_id": user_id,
        "__user_id__": user_id,
        "__started_at__": datetime.now(UTC).isoformat(),
    }


def render_markdown(report: dict[str, str], technical: dict[str, Any]) -> str:
    """Render both views of the report for the reviewer."""
    client = technical.get("client") or {}
    server = technical.get("server") or {}
    lines = [
        f"### {report['title']}",
        f"**Severity:** {SEVERITIES.get(report['severity'], report['severity'])}",
        "",
        "#### What happened",
        report["description"],
    ]
    if report.get("expected"):
        lines += ["", "#### Expected", report["expected"]]
    if report.get("steps"):
        lines += ["", "#### Steps to reproduce", report["steps"]]

    route = server.get("route") or {}
    version = server.get("version") or {}
    lines += [
        "",
        "#### Technical view",
        f"- **Page:** {client.get('url') or route.get('path') or 'unknown'}",
        f"- **View:** {route.get('view') or 'unknown'} {_inline(route.get('kwargs'))}",
        f"- **Build:** {version.get('short_hash', 'unknown')} {version.get('date', '')}".rstrip(),
        f"- **Reported at:** {server.get('received_at', '')}",
        f"- **Browser:** {client.get('user_agent') or server.get('user_agent') or 'unknown'}",
    ]
    viewport = client.get("viewport")
    if isinstance(viewport, dict):
        lines.append(f"- **Viewport:** {viewport.get('width')}×{viewport.get('height')}")
    if client.get("note"):
        lines.append(f"- **Client context:** {client['note']}")

    linked = technical.get("linked")
    if linked:
        lines += ["", "#### Linked state", _code_block(linked)]

    errors = client.get("errors") or []
    if errors:
        lines += ["", f"#### Recent browser errors ({len(errors)})", _code_block(errors)]
    failed = client.get("failed_requests") or []
    if failed:
        lines += ["", f"#### Failed requests ({len(failed)})", _code_block(failed)]
    return "\n".join(lines)


def _inline(value: Any) -> str:
    return f"`{json.dumps(value)}`" if value else ""


def _code_block(value: Any) -> str:
    return "```json\n" + json.dumps(value, indent=2, default=str) + "\n```"


def recent_bug_reports(limit: int = 50) -> list[dict[str, Any]]:
    """Return the newest *limit* bug reports, newest first (sync ORM)."""
    definition_ids = ProcessDefinitionModel.objects.filter(name=BUG_REPORT_WORKFLOW).values_list(
        "id", flat=True
    )
    models = ProcessInstanceModel.objects.filter(
        definition_id__in=list(definition_ids), parent_process_id__isnull=True
    ).order_by("-created_at")[:limit]
    return [summarize_report(m) for m in models]


def summarize_report(model: ProcessInstanceModel) -> dict[str, Any]:
    """Flatten one Bug Report process into the fields ``/bugs/`` shows."""
    props = json.loads(model.properties) if model.properties else {}
    report = props.get("bug_report") if isinstance(props.get("bug_report"), dict) else {}
    review = props.get(f"__task_output_{REVIEW_TASK}")
    review = review if isinstance(review, dict) else {}
    client = (props.get("technical_context") or {}).get("client") or {}
    issue_url = str(review.get("issue_url") or "")

    review_task_id = None
    if model.state == "running":
        review_task_id = (
            TaskInstanceModel.objects.filter(process_id=model.id, task_definition_id=REVIEW_TASK)
            .values_list("id", flat=True)
            .first()
        )

    return {
        "id": model.id,
        "state": model.state,
        "created_at": model.created_at,
        "title": report.get("title") or props.get("bug_title") or "(untitled)",
        "description": report.get("description", ""),
        "severity": report.get("severity", ""),
        "severity_label": SEVERITIES.get(report.get("severity", ""), report.get("severity", "")),
        "page": client.get("url", ""),
        "verdict": review.get("verdict"),
        "verdict_label": VERDICTS.get(review.get("verdict"), review.get("verdict")),
        "priority": review.get("priority"),
        "issue_url": issue_url if issue_url.startswith(("https://", "http://")) else None,
        "notes": review.get("notes"),
        "review_task_id": review_task_id,
        "markdown": props.get("bug_report_markdown", ""),
    }
