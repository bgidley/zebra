"""ProposeZebraImprovementsAction — dream-cycle requests for changes to Zebra (#189).

The rest of the dream cycle can only change workflows. Some problems it finds
need a change to Zebra's own code instead: an action that does not exist, an
engine limitation, a missing UI. This step gives an LLM the cycle's findings —
the evaluator's key issues and priorities, continuation capability gaps and the
optimizer's rejected changes — and asks only for those code-level problems.

Each proposal starts a *Zebra Improvement Request* process whose single human
task holds it for review (accept / reject / duplicate / later, optional issue
link). Requests are capped per cycle and never repeat an earlier request's
title. The step never fails the cycle.

``FileImprovementIssueAction`` runs after that review and files an accepted
request as a GitLab issue (#194).
"""

import json
import logging
import os
import re
from typing import Any
from urllib.parse import quote

import httpx
from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.llm.base import Message
from zebra_tasks.llm.client import get_llm, model_for
from zebra_tasks.llm.structured import LLMJSONError, complete_json

logger = logging.getLogger(__name__)

REQUEST_WORKFLOW = "Zebra Improvement Request"
REQUEST_MARKER = "__improvement_request__"
DEFAULT_MAX_REQUESTS = 2
MAX_ITEMS = 10  # findings of each kind shown to the LLM
CLIP = 400  # characters per finding shown to the LLM
AREAS = ("engine", "task_action", "web_ui", "storage", "llm", "other")
IMPACTS = ("high", "medium", "low")

SYSTEM_PROMPT = """You review the findings of an AI agent's self-improvement cycle.
The agent is Zebra, a workflow engine that runs YAML workflows built from registered task actions.
The cycle can already create and edit workflows itself. Your job is to spot problems that a
workflow edit CANNOT fix and that need a change to Zebra's own code, for example:
- a task action that does not exist or lacks an option (e.g. a rejected change needed it);
- an engine or routing limitation;
- a missing or broken web UI feature;
- a storage, cost-tracking or LLM-provider problem.

Ignore anything a workflow edit can fix. Be conservative: an empty list is a good answer.
Do not repeat a previous request, even reworded.

Return ONLY a JSON object:
{
  "requests": [
    {"title": "short imperative title",
     "area": "engine|task_action|web_ui|storage|llm|other",
     "problem": "what is wrong or missing",
     "evidence": "which findings show it",
     "suggested_change": "what to change in Zebra",
     "impact": "high|medium|low"}
  ]
}"""


def normalize_title(title: str) -> str:
    """Lower-case a title and collapse punctuation, for duplicate detection."""
    return re.sub(r"[^a-z0-9]+", " ", str(title).lower()).strip()


def _clip(value: Any, limit: int = CLIP) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= limit else text[:limit] + "…"


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def gather_findings(properties: dict[str, Any]) -> dict[str, list[str]]:
    """Collect the dream cycle's findings from its process properties."""
    evaluation = _dict(properties.get("evaluation"))
    optimization = _dict(properties.get("optimization_results"))
    continuations = _dict(_dict(properties.get("metrics_analysis")).get("continuation_analysis"))
    assessment = _dict(evaluation.get("overall_assessment"))

    def clipped(items: list) -> list[str]:
        return [_clip(i) for i in items[:MAX_ITEMS]]

    return {
        "key_issues": clipped(_list(assessment.get("key_issues"))),
        "improvement_priorities": clipped(_list(evaluation.get("improvement_priorities"))),
        "capability_gaps": clipped(_list(continuations.get("capability_gaps"))),
        "rejected_changes": clipped(_list(optimization.get("failed_changes"))),
    }


def render_markdown(request: dict[str, str]) -> str:
    """Render a request for the reviewer."""
    lines = [
        f"### {request['title']}",
        f"**Area:** {request['area']} · **Impact:** {request['impact']}",
        "",
        "#### Problem",
        request["problem"],
    ]
    if request.get("evidence"):
        lines += ["", "#### Evidence", request["evidence"]]
    if request.get("suggested_change"):
        lines += ["", "#### Suggested change", request["suggested_change"]]
    return "\n".join(lines)


def _validate(raw: Any) -> dict[str, str] | None:
    """Return a cleaned request, or None if it has no title or problem."""
    if not isinstance(raw, dict):
        return None
    title = str(raw.get("title") or "").strip()[:120]
    problem = str(raw.get("problem") or "").strip()
    if not title or not problem or not normalize_title(title):
        return None
    area = str(raw.get("area") or "other").strip().lower()
    impact = str(raw.get("impact") or "medium").strip().lower()
    return {
        "title": title,
        "area": area if area in AREAS else "other",
        "problem": problem[:1500],
        "evidence": str(raw.get("evidence") or "").strip()[:1500],
        "suggested_change": str(raw.get("suggested_change") or "").strip()[:1500],
        "impact": impact if impact in IMPACTS else "medium",
    }


class ProposeZebraImprovementsAction(TaskAction):
    """Ask a human for improvements to Zebra's code that the dream cycle cannot make.

    Reads the dream cycle's ``evaluation``, ``optimization_results`` and
    ``metrics_analysis`` process properties. Requires ``__workflow_library__``
    in ``context.extras`` to start request processes.

    Properties:
        max_requests: Requests started per cycle (default 2)
        provider / model: LLM override (default: the dream cycle's provider and model)
        output_key: Where to store the result (default ``improvement_requests``)
    """

    description = "Dream cycle: request human-reviewed improvements to Zebra's own code"
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(
            name="max_requests",
            type="int",
            description="Maximum requests started per cycle",
            required=False,
            default=DEFAULT_MAX_REQUESTS,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property for the result",
            required=False,
            default="improvement_requests",
        ),
    ]

    outputs = [
        ParameterDef(
            name="requests",
            type="list[dict]",
            description="Requests started: title, area, impact, process_id",
            required=True,
        ),
        ParameterDef(
            name="skipped",
            type="list[dict]",
            description="Proposals not started (duplicate or over the cap), with reason",
            required=True,
        ),
        ParameterDef(
            name="errors",
            type="list[string]",
            description="Problems that stopped or limited the step",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        output_key = task.properties.get("output_key", "improvement_requests")
        result = await self._propose(task, context)
        context.set_process_property(output_key, result)
        return TaskResult.ok(output=result)

    async def _propose(self, task: TaskInstance, context: ExecutionContext) -> dict[str, Any]:
        out: dict[str, Any] = {"requests": [], "skipped": [], "errors": []}

        findings = gather_findings(context.process.properties or {})
        if not any(findings.values()):
            logger.info("Improvement requests: no findings to review — skipping")
            return out

        library = context.extras.get("__workflow_library__")
        if library is None:
            logger.warning("Improvement requests: no workflow library — skipping")
            out["errors"].append("workflow library unavailable")
            return out
        try:
            definition = library.get_workflow(REQUEST_WORKFLOW)
        except Exception as e:
            logger.warning("Improvement requests: %s workflow not found: %s", REQUEST_WORKFLOW, e)
            out["errors"].append(f"{REQUEST_WORKFLOW} workflow not found")
            return out

        provider = get_llm(model_for(task, context), context)

        earlier = await self._earlier_titles(context)
        proposals = await self._ask(provider, context, findings, earlier, out)

        max_requests = int(task.properties.get("max_requests", DEFAULT_MAX_REQUESTS))
        seen = {normalize_title(t) for t in earlier}
        for raw in proposals:
            request = _validate(raw)
            if request is None:
                out["skipped"].append({"title": _clip(raw, 120), "reason": "invalid"})
                continue
            key = normalize_title(request["title"])
            if key in seen:
                out["skipped"].append({"title": request["title"], "reason": "duplicate"})
                continue
            if len(out["requests"]) >= max_requests:
                out["skipped"].append({"title": request["title"], "reason": "over cap"})
                continue
            seen.add(key)
            try:
                process_id = await self._start(context, definition, request, key)
            except Exception as e:
                logger.warning("Improvement requests: could not start request: %s", e)
                out["errors"].append(f"could not start '{request['title']}': {e}")
                continue
            out["requests"].append(
                {
                    "title": request["title"],
                    "area": request["area"],
                    "impact": request["impact"],
                    "process_id": process_id,
                }
            )
        return out

    async def _earlier_titles(self, context: ExecutionContext) -> list[str]:
        """Titles of every earlier request, in any state and any workflow version.

        A definition's id is derived from its name and version, so each stored
        version of the request workflow is looked up (#194).
        """
        try:
            definition_ids = [
                d.id for d in await context.store.list_definitions() if d.name == REQUEST_WORKFLOW
            ]
            processes = []
            for definition_id in definition_ids:
                processes += await context.store.list_processes(
                    definition_id=definition_id, include_completed=True
                )
        except Exception as e:
            logger.warning("Improvement requests: could not list earlier requests: %s", e)
            return []
        return [
            str(p.properties.get("improvement_title"))
            for p in processes
            if (p.properties or {}).get("improvement_title")
        ]

    async def _ask(
        self,
        provider: Any,
        context: ExecutionContext,
        findings: dict[str, list[str]],
        earlier: list[str],
        out: dict[str, Any],
    ) -> list[Any]:
        prompt = (
            "## Findings of this cycle\n"
            + json.dumps(findings, indent=2)
            + "\n\n## Previous requests (do not repeat)\n"
            + (json.dumps(earlier[-50:], indent=2) if earlier else "none")
        )
        try:
            data = await complete_json(
                provider,
                [Message.system(SYSTEM_PROMPT), Message.user(prompt)],
                temperature=0.2,
                max_tokens=1500,
            )
        except LLMJSONError as e:
            logger.warning("Improvement requests: unparseable LLM response: %s", e)
            out["errors"].append(f"unparseable LLM response: {e}")
            return []
        except Exception as e:
            logger.warning("Improvement requests: LLM call failed: %s", e)
            out["errors"].append(f"LLM call failed: {e}")
            return []
        return _list(data.get("requests")) if isinstance(data, dict) else []

    async def _start(
        self,
        context: ExecutionContext,
        definition: Any,
        request: dict[str, str],
        marker: str,
    ) -> str:
        properties: dict[str, Any] = {
            "goal": f"Zebra improvement: {request['title']}",
            "improvement": request,
            "improvement_title": request["title"],
            "improvement_markdown": render_markdown(request),
            "source_process_id": context.process.id,
            REQUEST_MARKER: marker,
        }
        user_id = context.process.properties.get("__user_id__")
        if user_id is not None:
            properties["__user_id__"] = user_id
        process = await context.engine.create_process(definition, properties=properties)
        await context.engine.start_process(process.id)
        logger.info("Improvement requests: '%s' → process %s", request["title"], process.id)
        return process.id


# ---------------------------------------------------------------------------
# Filing accepted requests as GitLab issues (#194)
# ---------------------------------------------------------------------------

REVIEW_OUTPUT = "__task_output_review"
ISSUE_LABEL = "dream-request"
ISSUE_MARKER_PREFIX = "zebra-request:"
DEFAULT_GITLAB_URL = "https://gitlab.com"
DEFAULT_GITLAB_PROJECT = "gidley/zebra"
GITLAB_TIMEOUT = 15.0
ZERO_WIDTH_SPACE = "​"


def neutralize(text: str) -> str:
    """Stop text from running GitLab quick actions or mentioning anyone.

    GitLab runs a quick action for a line whose first character is ``/``
    (leading spaces allowed), so such lines get a backslash, which Markdown
    renders away. ``@`` gets a zero-width space so it is never a mention.
    """
    lines = []
    for line in str(text).replace("@", "@" + ZERO_WIDTH_SPACE).split("\n"):
        if line.lstrip().startswith("/"):
            indent = line[: len(line) - len(line.lstrip())]
            line = indent + "\\" + line.lstrip()
        lines.append(line)
    return "\n".join(lines)


def issue_marker(process_id: str) -> str:
    """Marker written into the issue body so a re-run can find the issue it made."""
    return f"{ISSUE_MARKER_PREFIX}{process_id}"


def build_issue(properties: dict[str, Any], process_id: str) -> tuple[str, str]:
    """Title and body of the GitLab issue for an accepted request."""
    improvement = _dict(properties.get("improvement"))
    review = _dict(properties.get(REVIEW_OUTPUT))
    title = improvement.get("title") or properties.get("improvement_title") or "Zebra improvement"
    body = str(properties.get("improvement_markdown") or improvement.get("problem") or "")
    if review.get("notes"):
        body += f"\n\n#### Reviewer notes\n{review['notes']}"
    source = properties.get("source_process_id")
    body += (
        "\n\n---\nRaised by Zebra's dream cycle"
        + (f" (process `{source}`)" if source else "")
        + " and accepted on /dreams/. Refs #189."
    )
    return neutralize(str(title))[:255], neutralize(body) + f"\n\n`{issue_marker(process_id)}`"


class FileImprovementIssueAction(TaskAction):
    """File an accepted *Zebra Improvement Request* as a GitLab issue (#194).

    Runs after the request's ``review`` human task. Files one issue only when
    the verdict is ``accepted`` and the reviewer gave no issue link; skips when
    an issue was already filed. Before creating, it searches the project for an
    issue carrying this request's marker, so a re-run after a crash adopts that
    issue instead of filing a second one.

    Env:
        ZEBRA_GITLAB_TOKEN: token with ``api`` scope (required to file)
        ZEBRA_GITLAB_URL: GitLab base URL (default ``https://gitlab.com``)
        ZEBRA_GITLAB_PROJECT: project path (default ``gidley/zebra``)

    Writes ``filed_issue`` = ``{url, iid}``, ``{skipped}`` or ``{error}``.
    Never fails the request; the token never appears in outputs or logs.
    """

    description = "File an accepted Zebra improvement request as a GitLab issue"
    reversibility_hint = "always_irreversible"

    inputs = [
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property for the result",
            required=False,
            default="filed_issue",
        ),
    ]

    outputs = [
        ParameterDef(name="url", type="string", description="Issue URL", required=False),
        ParameterDef(name="iid", type="int", description="Issue number", required=False),
        ParameterDef(name="skipped", type="string", description="Why nothing was filed"),
        ParameterDef(name="error", type="string", description="Why filing failed"),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        output_key = task.properties.get("output_key", "filed_issue")
        result = await self._file(context, output_key)
        context.set_process_property(output_key, result)
        return TaskResult.ok(output=result)

    async def _file(self, context: ExecutionContext, output_key: str) -> dict[str, Any]:
        properties = context.process.properties or {}
        review = _dict(properties.get(REVIEW_OUTPUT))
        previous = _dict(properties.get(output_key))
        if previous.get("url"):
            return {**previous, "skipped": "already filed"}
        if review.get("verdict") != "accepted":
            return {"skipped": "not accepted"}
        if str(review.get("issue_url") or "").strip():
            return {"skipped": "reviewer linked an issue"}

        token = os.environ.get("ZEBRA_GITLAB_TOKEN", "").strip()
        if not token:
            logger.warning("Improvement issue: ZEBRA_GITLAB_TOKEN is not set — not filing")
            return {"error": "ZEBRA_GITLAB_TOKEN is not set"}
        base = os.environ.get("ZEBRA_GITLAB_URL", DEFAULT_GITLAB_URL).rstrip("/")
        project = os.environ.get("ZEBRA_GITLAB_PROJECT", DEFAULT_GITLAB_PROJECT)
        issues_url = f"{base}/api/v4/projects/{quote(project, safe='')}/issues"
        marker = issue_marker(context.process.id)
        title, body = build_issue(properties, context.process.id)

        try:
            async with httpx.AsyncClient(
                timeout=GITLAB_TIMEOUT, headers={"PRIVATE-TOKEN": token}
            ) as client:
                found = await client.get(
                    issues_url,
                    params={"search": marker, "in": "description", "state": "all", "per_page": 20},
                )
                if found.status_code != 200:
                    # Without the search we can't rule out an issue filed by a crashed run.
                    logger.warning("Improvement issue: search returned %d", found.status_code)
                    return {"error": f"GitLab search returned {found.status_code}; not filing"}
                for issue in found.json() or []:
                    if f"`{marker}`" in str(issue.get("description") or ""):
                        logger.info("Improvement issue: adopting existing issue for %s", marker)
                        return {"url": issue.get("web_url"), "iid": issue.get("iid")}
                response = await client.post(
                    issues_url, json={"title": title, "description": body, "labels": ISSUE_LABEL}
                )
        except httpx.TimeoutException:
            logger.warning("Improvement issue: GitLab timed out")
            return {"error": f"GitLab did not answer within {GITLAB_TIMEOUT:.0f}s"}
        except httpx.RequestError as e:
            logger.warning("Improvement issue: network error: %s", type(e).__name__)
            return {"error": f"network error calling GitLab: {type(e).__name__}"}

        if response.status_code != 201:
            detail = response.text[:200].replace(token, "***")
            logger.warning("Improvement issue: GitLab returned %d", response.status_code)
            return {"error": f"GitLab returned {response.status_code}: {detail}"}
        issue = response.json()
        logger.info("Improvement issue: filed %s", issue.get("web_url"))
        return {"url": issue.get("web_url"), "iid": issue.get("iid")}
