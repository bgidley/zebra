"""Confidentiality scan of a workflow before it moves between spheres (#236, S3b-1).

``commons_confidentiality_scan`` looks for what an employer (or a household) would not want
to leave its sphere: internal hostnames and private addresses, URLs, project codenames,
customer names, credentials, and the device's own ``SYNC_CONFIDENTIAL_PATTERNS``. Rules run
first, then one low-tier LLM call over every string of the workflow (no ``commons`` block).

It **fails closed**: the route is ``clean`` only when the rules find nothing and the LLM
answers ``confidential: false``. A finding, unparseable YAML, a bad pattern, too much text,
no LLM or an unusable reply routes ``rejected``. Run on a work device it is the
data-security boundary; the receiver runs it again.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re
from typing import Any

import yaml
from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.commons.pii_scan import (
    _CRED_URL_RE,
    _SECRET_RES,
    _TEMPLATE_RE,
    DEFAULT_MAX_CHARS,
    ScanText,
    _llm_payload,
    _mask,
    _reserved_domain,
    collect_texts,
)
from zebra_tasks.knowledge.extract import resolve_raw
from zebra_tasks.llm.base import Message
from zebra_tasks.llm.client import get_llm, model_for
from zebra_tasks.llm.structured import complete_json

logger = logging.getLogger(__name__)

ROUTE_CLEAN = "clean"
ROUTE_REJECTED = "rejected"
PATTERNS_ENV = "ZEBRA_SYNC_CONFIDENTIAL_PATTERNS"

_INTERNAL_HOST_RE = re.compile(
    r"\b(?:[a-z0-9-]+\.)+(?:internal|corp|local|lan|intranet|private|home\.arpa)\b",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"\b(?:https?|ftp|wss?)://([^/\s:@?#'\"]+)", re.IGNORECASE)
_IPV4_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
_CODENAME_RE = re.compile(r"\b(?:[Pp]roject|[Oo]peration|[Cc]ode ?name)[:\s]+[A-Z][A-Za-z0-9]{2,}")
_CUSTOMER_RE = re.compile(
    r"\b(?:for|with|from|of|at)\s+(?:the\s+)?(?:customer|client|account)\s+[A-Z][\w&-]+"
)
_CREDENTIAL_RE = re.compile(
    r"\b(?:password|passwd|pwd|api[_-]?key|secret|access[_-]?token|token)\s*[:=]\s*\S{6,}",
    re.IGNORECASE,
)

SYSTEM_PROMPT = """You check a workflow definition before it is copied from one of a \
person's devices to another (for example from a work laptop to a home server). Find \
confidential material that must not leave where it was learnt: internal hostnames or \
systems, project or product codenames, customer, client or supplier names, employer- \
internal facts (prices, deals, incidents, org details), credentials or secrets, and \
internal URLs.

Not confidential: generic instructions, {{template}} placeholders, public tools and \
services (GitHub, Python, Wikipedia), obviously fictional sample data and technical \
settings.

Reply with JSON only:
{"confidential": true|false,
 "findings": [{"path": "<path given>", "kind": "<host|codename|customer|credential|url|internal>", \
"reason": "<short reason, do not repeat the text>"}]}"""


def configured_patterns(extra: Any = None) -> list[str]:
    """``SYNC_CONFIDENTIAL_PATTERNS`` (env, one regex per line or ``;;``) plus *extra*."""
    patterns: list[str] = []
    raw = os.environ.get(PATTERNS_ENV, "")
    for chunk in re.split(r"\n|;;", raw):
        if chunk.strip():
            patterns.append(chunk.strip())
    if isinstance(extra, str):
        extra = [extra]
    for item in extra or []:
        if isinstance(item, str) and item.strip():
            patterns.append(item.strip())
    return patterns


def _private_ip(text: str) -> bool:
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return False
    return ip.is_private and not ip.is_loopback


def confidential_rule_findings(
    texts: list[ScanText], patterns: list[re.Pattern[str]]
) -> list[dict[str, str]]:
    """What the rules find; ``{{templates}}`` and reserved example domains are skipped."""
    findings: list[dict[str, str]] = []

    def hit(kind: str, item: ScanText, match: str) -> None:
        findings.append({"source": "rule", "kind": kind, "path": item.path, "text": _mask(match)})

    for item in texts:
        text = _TEMPLATE_RE.sub(" ", item.text)
        for m in _INTERNAL_HOST_RE.finditer(text):
            hit("internal_host", item, m.group(0))
        for m in _URL_RE.finditer(text):
            if not _reserved_domain(m.group(1)):
                hit("url", item, m.group(0))
        for m in _IPV4_RE.finditer(text):
            if _private_ip(m.group(0)):
                hit("internal_host", item, m.group(0))
        for m in _CODENAME_RE.finditer(text):
            hit("codename", item, m.group(0))
        for m in _CUSTOMER_RE.finditer(text):
            hit("customer", item, m.group(0))
        for m in _CREDENTIAL_RE.finditer(text):
            hit("credential", item, m.group(0))
        for m in _CRED_URL_RE.finditer(text):
            hit("credential", item, m.group(0))
        for pattern in _SECRET_RES:
            for m in pattern.finditer(text):
                hit("credential", item, m.group(0))
        for pattern in patterns:
            for m in pattern.finditer(text):
                hit("confidential_pattern", item, m.group(0))
    return findings


def _result(clean: bool, reason: str, findings=None, *, failed: bool = False, scanned: int = 0):
    return {
        "clean": clean,
        "findings": findings or [],
        "failed_closed": failed,
        "reason": reason,
        "texts_scanned": scanned,
    }


async def scan_confidential(
    raw_yaml: Any,
    *,
    patterns: list[str],
    llm: Any,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> dict[str, Any]:
    """Scan workflow YAML; ``llm`` is a provider or None (fails closed).

    Returns ``{clean, findings, failed_closed, reason, texts_scanned}``.
    """
    if not isinstance(raw_yaml, str) or not raw_yaml.strip():
        return _result(False, "no workflow YAML to scan — failing closed", failed=True)
    try:
        workflow = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as e:
        return _result(False, f"workflow YAML does not parse — failing closed: {e}", failed=True)
    if not isinstance(workflow, dict):
        return _result(False, "workflow YAML is not a mapping — failing closed", failed=True)
    try:
        compiled = [re.compile(p, re.IGNORECASE) for p in patterns]
    except re.error as e:
        return _result(False, f"bad confidential pattern — failing closed: {e}", failed=True)
    texts = collect_texts(workflow)
    scanned = len(texts)
    findings = confidential_rule_findings(texts, compiled)
    if findings:
        return _result(False, "confidential material found by rules", findings, scanned=scanned)
    payload = _llm_payload(texts)
    if len(payload) > max_chars:
        return _result(
            False,
            f"{len(payload)} characters is more than the scan limit {max_chars} — failing closed",
            failed=True,
            scanned=scanned,
        )
    if llm is None:
        return _result(False, "no LLM for the scan — failing closed", failed=True, scanned=scanned)
    try:
        reply = await complete_json(
            llm,
            [Message.system(SYSTEM_PROMPT), Message.user(payload)],
            temperature=0.0,
            max_tokens=1500,
        )
    except Exception as e:  # provider error, unusable JSON
        logger.warning("Confidentiality scan: LLM check failed (%s) — failing closed", e)
        return _result(
            False, f"LLM check failed — failing closed: {e}", failed=True, scanned=scanned
        )
    if not isinstance(reply, dict) or not isinstance(reply.get("confidential"), bool):
        return _result(
            False,
            "LLM reply has no confidential verdict — failing closed",
            failed=True,
            scanned=scanned,
        )
    llm_findings = [
        {
            "source": "llm",
            "kind": str(f.get("kind", "confidential"))[:40],
            "path": str(f.get("path", ""))[:200],
            "reason": str(f.get("reason", ""))[:300],
        }
        for f in reply.get("findings") or []
        if isinstance(f, dict)
    ]
    if reply["confidential"] or llm_findings:
        findings = llm_findings or [
            {"source": "llm", "kind": "confidential", "path": "", "reason": "flagged"}
        ]
        return _result(False, "confidential material found by the LLM", findings, scanned=scanned)
    return _result(True, "nothing confidential found by rules or LLM", scanned=scanned)


class CommonsConfidentialityScanAction(TaskAction):
    """Scan a workflow for confidential material; route ``clean`` or ``rejected``.

    Properties:
        yaml: The workflow YAML (template-resolved)
        patterns: Extra regexes (list or string); the device's
            ``SYNC_CONFIDENTIAL_PATTERNS`` (``__commons_sync__.confidential_patterns``,
            else the env var) always apply
        model: LLM tier (default ``low``)
        max_chars: Most text the LLM is shown; more fails closed (default 60000)
        output_key: Process property for the result (default ``confidentiality_scan``)
    """

    description = (
        "Scan a workflow for internal hosts, codenames, customer names, credentials, URLs and "
        "the device's confidential patterns, with rules and a low-tier LLM; fails closed."
    )
    # Reads and one LLM call; nothing outside this run changes (#245 convention).
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(name="yaml", type="string", description="Workflow YAML", required=True),
        ParameterDef(name="patterns", type="array", description="Extra regexes", required=False),
        ParameterDef(name="model", type="string", description="LLM tier", required=False),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property for the result",
            required=False,
            default="confidentiality_scan",
        ),
    ]
    outputs = [
        ParameterDef(name="clean", type="boolean", description="Nothing found", required=True),
        ParameterDef(name="findings", type="array", description="What was found", required=True),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Scan, store the result under ``output_key`` and route."""
        sync = context.extras.get("__commons_sync__")
        extra = list(getattr(sync, "confidential_patterns", None) or [])
        extra += configured_patterns(resolve_raw(context, task.properties.get("patterns")))
        try:
            llm = get_llm(model_for(task, context, default="low"), context)
        except Exception as e:  # no provider configured
            logger.warning("Confidentiality scan: no LLM (%s) — failing closed", e)
            llm = None
        try:
            max_chars = int(task.properties.get("max_chars", DEFAULT_MAX_CHARS))
        except (TypeError, ValueError):
            max_chars = DEFAULT_MAX_CHARS
        result = await scan_confidential(
            resolve_raw(context, task.properties.get("yaml")),
            patterns=extra,
            llm=llm,
            max_chars=max_chars,
        )
        context.set_process_property(
            task.properties.get("output_key", "confidentiality_scan"), result
        )
        route = ROUTE_CLEAN if result["clean"] else ROUTE_REJECTED
        logger.info("Confidentiality scan: %s (%d findings)", route, len(result["findings"]))
        return TaskResult(success=True, output=result, next_route=route)
