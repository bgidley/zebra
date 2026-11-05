"""Sensitivity check of a workflow for a target sphere (#236, S3b-1).

``commons_sensitivity_check`` asks a low-tier LLM: "would this workflow's name, purpose or
content be sensitive if seen in sphere X?" (job searching, health, money, HR, legal,
relationships and similar). Routes ``not_sensitive`` or ``sensitive``, and **fails closed**
to ``sensitive`` on bad YAML, no LLM, a provider error or a reply without a boolean
``sensitive``. Skill sync never proposes a sensitive workflow to an observed sphere.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import yaml
from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.commons.pii_scan import DEFAULT_MAX_CHARS
from zebra_tasks.knowledge.extract import resolve_raw
from zebra_tasks.llm.base import Message
from zebra_tasks.llm.client import get_llm, model_for
from zebra_tasks.llm.structured import complete_json

logger = logging.getLogger(__name__)

ROUTE_NOT_SENSITIVE = "not_sensitive"
ROUTE_SENSITIVE = "sensitive"

SYSTEM_PROMPT = """You decide whether a workflow (an AI assistant's reusable procedure) \
would be sensitive if someone in another part of its owner's life saw it. The owner runs \
the same assistant in several spheres (e.g. home and work). An "observed" sphere is a \
device managed by someone else, such as an employer's laptop with monitoring and IT access.

Sensitive means its name, purpose or content reveals something the owner may not want seen \
there: job searching or leaving a job, health, money or debt, HR or legal matters, \
relationships or family matters, politics or religion, and similar personal topics. \
Ordinary work or household procedures are not sensitive.

Reply with JSON only:
{"sensitive": true|false, "topics": ["<topic>"], "reason": "<one short sentence>"}"""


def _result(sensitive: bool, reason: str, topics=None, *, failed: bool = False) -> dict:
    return {
        "sensitive": sensitive,
        "topics": topics or [],
        "reason": reason,
        "failed_closed": failed,
    }


async def check_sensitivity(
    raw_yaml: Any,
    *,
    sphere: str,
    observed: bool,
    llm: Any,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> dict[str, Any]:
    """Return ``{sensitive, topics, reason, failed_closed}``; any failure is sensitive."""
    if not isinstance(raw_yaml, str) or not raw_yaml.strip():
        return _result(True, "no workflow YAML — failing closed", failed=True)
    try:
        workflow = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as e:
        return _result(True, f"workflow YAML does not parse — failing closed: {e}", failed=True)
    if not isinstance(workflow, dict):
        return _result(True, "workflow YAML is not a mapping — failing closed", failed=True)
    body = {k: v for k, v in workflow.items() if k != "commons"}
    text = json.dumps(body, ensure_ascii=False, default=str)
    if len(text) > max_chars:
        return _result(True, "workflow too large to check — failing closed", failed=True)
    if llm is None:
        return _result(True, "no LLM for the check — failing closed", failed=True)
    prompt = (
        f"Target sphere: {sphere} ({'observed' if observed else 'not observed'}).\n"
        f"Workflow:\n{text}"
    )
    try:
        reply = await complete_json(
            llm,
            [Message.system(SYSTEM_PROMPT), Message.user(prompt)],
            temperature=0.0,
            max_tokens=500,
        )
    except Exception as e:
        logger.warning("Sensitivity check: LLM failed (%s) — failing closed", e)
        return _result(True, f"LLM check failed — failing closed: {e}", failed=True)
    if not isinstance(reply, dict) or not isinstance(reply.get("sensitive"), bool):
        return _result(True, "LLM reply has no sensitive verdict — failing closed", failed=True)
    topics = [str(t)[:40] for t in reply.get("topics") or [] if isinstance(t, str)][:5]
    return _result(reply["sensitive"], str(reply.get("reason") or "")[:300], topics)


class CommonsSensitivityCheckAction(TaskAction):
    """Would this workflow be sensitive in the target sphere? Routes ``sensitive`` or not.

    Properties:
        yaml: The workflow YAML (template-resolved)
        sphere: The target sphere
        observed: Whether the target sphere is observed
        model: LLM tier (default ``low``)
        output_key: Process property for the result (default ``sensitivity``)
    """

    description = (
        "Ask a low-tier LLM whether a workflow would be sensitive (job search, health, money, "
        "HR, legal, relationships) if seen in a target sphere; fails closed to sensitive."
    )
    # One LLM call; nothing outside this run changes (#245 convention).
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(name="yaml", type="string", description="Workflow YAML", required=True),
        ParameterDef(name="sphere", type="string", description="Target sphere", required=True),
        ParameterDef(
            name="observed", type="boolean", description="Target is observed", required=False
        ),
        ParameterDef(name="model", type="string", description="LLM tier", required=False),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property for the result",
            required=False,
            default="sensitivity",
        ),
    ]
    outputs = [
        ParameterDef(name="sensitive", type="boolean", description="Sensitive", required=True),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Check, store the result under ``output_key`` and route."""
        observed = resolve_raw(context, task.properties.get("observed"))
        if isinstance(observed, str):
            observed = observed.strip().lower() in ("true", "1", "yes")
        try:
            llm = get_llm(model_for(task, context, default="low"), context)
        except Exception as e:
            logger.warning("Sensitivity check: no LLM (%s) — failing closed", e)
            llm = None
        result = await check_sensitivity(
            resolve_raw(context, task.properties.get("yaml")),
            sphere=str(resolve_raw(context, task.properties.get("sphere")) or ""),
            observed=bool(observed),
            llm=llm,
        )
        context.set_process_property(task.properties.get("output_key", "sensitivity"), result)
        route = ROUTE_SENSITIVE if result["sensitive"] else ROUTE_NOT_SENSITIVE
        logger.info("Sensitivity check: %s (%s)", route, result["reason"])
        return TaskResult(success=True, output=result, next_route=route)
