"""Personal-data scan of a workflow before it leaves the deployment (#229 S2b, REQ-NET-002).

``commons_pii_scan`` checks every string in a workflow (prompts, defaults, examples,
descriptions; not the ``commons`` block) and its golden tasks, first with rules
(emails, phone numbers, card numbers, UK NI numbers and postcodes, IP addresses,
secrets, URLs with credentials), then with one low-tier LLM call for what rules miss
(names, addresses, health or family details of real people).

It **fails closed**: the route is ``clean`` only when the rules find nothing and the
LLM answers ``personal_data: false``. Anything else (a finding, unparseable YAML, too
much text, no LLM, an unusable reply) routes ``rejected``.

The workflow text goes to the LLM provider (OpenRouter), as every LLM-written workflow
already does; the scan exists to stop it going anywhere wider.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import yaml
from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.knowledge.extract import resolve_raw
from zebra_tasks.llm.base import Message
from zebra_tasks.llm.client import get_llm, model_for
from zebra_tasks.llm.structured import complete_json

logger = logging.getLogger(__name__)

ROUTE_CLEAN = "clean"
ROUTE_REJECTED = "rejected"
DEFAULT_MAX_CHARS = 60_000

_TEMPLATE_RE = re.compile(r"\{\{.*?\}\}", re.DOTALL)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})")
_PHONE_RE = re.compile(r"(?<![\w.])\+?\(?\d[\d\s().-]{7,}\d(?![\w])")
_CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_NI_RE = re.compile(r"\b[A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z] ?\d{2} ?\d{2} ?\d{2} ?[A-D]\b")
_POSTCODE_RE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]? \d[A-Z]{2}\b")
_IPV4_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
_CRED_URL_RE = re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@", re.IGNORECASE)
_SECRET_RES = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\b(?:ghp|gho|ghs|github_pat)_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bxox[abpr]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bnsec1[02-9ac-hj-np-z]{20,}"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{20,}=*"),
)
# Reserved for documentation and tests (RFC 2606 / 6761): never personal data.
_RESERVED_DOMAINS = ("example.com", "example.org", "example.net")
_RESERVED_TLDS = (".example", ".test", ".invalid", ".localhost")
_DOC_NETWORKS = tuple(
    ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")
)

SYSTEM_PROMPT = """You check a workflow definition before it is shared with other people's \
AI assistants. Find personal data: anything that identifies or describes a specific real, \
private person or household — names, contact details, home or work addresses, account or \
ID numbers, health, financial, family, relationship or location details, private schedules, \
employer-confidential facts, credentials or secrets.

Not personal data: generic instructions, {{template}} placeholders, public organisations, \
public figures named only as examples, obviously fictional sample data (Jane Doe, \
example.com), and technical settings.

Reply with JSON only:
{"personal_data": true|false,
 "findings": [{"path": "<path given>", "kind": "<name|contact|address|health|...>", \
"reason": "<short reason, do not repeat the data>"}]}"""


@dataclass(frozen=True)
class ScanText:
    """One string from the workflow or golden tasks, with where it came from."""

    path: str
    text: str


def collect_texts(workflow: Any, golden_tasks: Any = None) -> list[ScanText]:
    """Every string (values and keys) of the workflow, minus its ``commons`` block, and of
    the golden tasks."""
    found: list[ScanText] = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, str):
            if value.strip():
                found.append(ScanText(path, value))
        elif isinstance(value, dict):
            for key, item in value.items():
                child = f"{path}.{key}" if path else str(key)
                if isinstance(key, str) and len(key) > 2:
                    walk(key, f"{child} (key)")
                walk(item, child)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                walk(item, f"{path}[{i}]")

    if isinstance(workflow, dict):
        walk({k: v for k, v in workflow.items() if k != "commons"}, "")
    if golden_tasks:
        walk(golden_tasks if isinstance(golden_tasks, list) else [golden_tasks], "golden_tasks")
    return found


def _mask(text: str) -> str:
    text = text.strip()
    return f"{text[:2]}…({len(text)} chars)" if len(text) > 4 else "…"


def _luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
    return total % 10 == 0


def _reserved_domain(domain: str) -> bool:
    domain = domain.lower()
    if domain.endswith(_RESERVED_TLDS) or domain == "localhost":
        return True
    return any(domain == d or domain.endswith("." + d) for d in _RESERVED_DOMAINS)


def _public_ip(text: str) -> bool:
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return False
    if ip.is_loopback or ip.is_unspecified or any(ip in n for n in _DOC_NETWORKS):
        return False
    return True


def rule_findings(texts: list[ScanText]) -> list[dict[str, str]]:
    """Personal data the rules find; ``{{templates}}`` and reserved examples are skipped."""
    findings: list[dict[str, str]] = []

    def hit(kind: str, item: ScanText, match: str) -> None:
        findings.append({"source": "rule", "kind": kind, "path": item.path, "text": _mask(match)})

    for item in texts:
        text = _TEMPLATE_RE.sub(" ", item.text)
        for m in _EMAIL_RE.finditer(text):
            if not _reserved_domain(m.group(1)):
                hit("email", item, m.group(0))
        for m in _CRED_URL_RE.finditer(text):
            hit("url_credentials", item, m.group(0))
        for pattern in _SECRET_RES:
            for m in pattern.finditer(text):
                hit("secret", item, m.group(0))
        for m in _NI_RE.finditer(text):
            hit("ni_number", item, m.group(0))
        for m in _POSTCODE_RE.finditer(text):
            hit("postcode", item, m.group(0))
        ips = set()
        for m in _IPV4_RE.finditer(text):
            if _public_ip(m.group(0)):
                ips.add(m.group(0))
                hit("ip_address", item, m.group(0))
        cards = set()
        for m in _CARD_RE.finditer(text):
            digits = re.sub(r"\D", "", m.group(0))
            if 13 <= len(digits) <= 19 and _luhn(digits):
                cards.add(m.group(0))
                hit("card_number", item, m.group(0))
        for m in _PHONE_RE.finditer(text):
            candidate = m.group(0).strip()
            digits = re.sub(r"\D", "", candidate)
            if candidate in ips or candidate in cards or not 10 <= len(digits) <= 15:
                continue
            separated = bool(re.search(r"\d[\s().-]+\d", candidate))
            if candidate[0] in "+(0" or separated:
                hit("phone", item, candidate)
    return findings


def _llm_payload(texts: list[ScanText]) -> str:
    return json.dumps([{"path": t.path, "text": t.text} for t in texts], ensure_ascii=False)


class CommonsPiiScanAction(TaskAction):
    """Scan a workflow and its golden tasks for personal data; route ``clean`` or ``rejected``.

    Properties:
        yaml: The workflow YAML (template-resolved)
        golden_tasks: Golden tasks (list of strings or mappings), optional
        model: LLM tier (default ``low``)
        max_chars: Most text the LLM is shown; more fails closed (default 60000)
        output_key: Process property for the result (default ``pii_scan``)

    Output: ``{clean, findings: [{source, kind, path, text (masked) | reason}],
    failed_closed, reason, texts_scanned}``.
    """

    description = (
        "Scan a workflow (prompts, defaults, examples) and its golden tasks for personal "
        "data with rules and a low-tier LLM before it is shared; fails closed."
    )
    # Reads and one LLM call; nothing outside this run changes (#245 convention).
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(name="yaml", type="string", description="Workflow YAML", required=True),
        ParameterDef(
            name="golden_tasks",
            type="array",
            description="Golden tasks shipped with the workflow",
            required=False,
        ),
        ParameterDef(name="model", type="string", description="LLM tier", required=False),
        ParameterDef(
            name="max_chars",
            type="number",
            description="Most text shown to the LLM; more fails closed",
            required=False,
            default=DEFAULT_MAX_CHARS,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property for the result",
            required=False,
            default="pii_scan",
        ),
    ]
    outputs = [
        ParameterDef(name="clean", type="boolean", description="No personal data", required=True),
        ParameterDef(name="findings", type="array", description="What was found", required=True),
        ParameterDef(
            name="failed_closed",
            type="boolean",
            description="The scan could not complete and rejected",
            required=True,
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Scan, store the result under ``output_key`` and route."""
        result = await self._scan(task, context)
        context.set_process_property(task.properties.get("output_key", "pii_scan"), result)
        route = ROUTE_CLEAN if result["clean"] else ROUTE_REJECTED
        logger.info(
            "Personal-data scan: %s (%d findings%s)",
            route,
            len(result["findings"]),
            ", failed closed" if result["failed_closed"] else "",
        )
        return TaskResult(success=True, output=result, next_route=route)

    async def _scan(self, task: TaskInstance, context: ExecutionContext) -> dict[str, Any]:
        def rejected(reason: str, findings=None, *, failed: bool, scanned: int = 0) -> dict:
            return {
                "clean": False,
                "findings": findings or [],
                "failed_closed": failed,
                "reason": reason,
                "texts_scanned": scanned,
            }

        raw_yaml = resolve_raw(context, task.properties.get("yaml"))
        if not isinstance(raw_yaml, str) or not raw_yaml.strip():
            return rejected("no workflow YAML to scan — failing closed", failed=True)
        try:
            workflow = yaml.safe_load(raw_yaml)
        except yaml.YAMLError as e:
            return rejected(f"workflow YAML does not parse — failing closed: {e}", failed=True)
        if not isinstance(workflow, dict):
            return rejected("workflow YAML is not a mapping — failing closed", failed=True)
        golden = resolve_raw(context, task.properties.get("golden_tasks"))
        if isinstance(golden, str) and golden.strip():
            try:
                golden = json.loads(golden)
            except ValueError:
                golden = [golden]
        texts = collect_texts(workflow, golden or None)
        scanned = len(texts)

        findings = rule_findings(texts)
        if findings:
            return rejected("personal data found by rules", findings, failed=False, scanned=scanned)

        payload = _llm_payload(texts)
        try:
            max_chars = int(task.properties.get("max_chars", DEFAULT_MAX_CHARS))
        except (TypeError, ValueError):
            max_chars = DEFAULT_MAX_CHARS
        if len(payload) > max_chars:
            return rejected(
                f"{len(payload)} characters is more than the scan limit {max_chars} "
                "— failing closed",
                failed=True,
                scanned=scanned,
            )
        try:
            llm = get_llm(model_for(task, context, default="low"), context)
            reply = await complete_json(
                llm,
                [Message.system(SYSTEM_PROMPT), Message.user(payload)],
                temperature=0.0,
                max_tokens=1500,
            )
        except Exception as e:  # no provider, provider error, unusable JSON
            logger.warning("Personal-data scan: LLM check failed (%s) — failing closed", e)
            return rejected(f"LLM check failed — failing closed: {e}", failed=True, scanned=scanned)
        if not isinstance(reply, dict) or not isinstance(reply.get("personal_data"), bool):
            return rejected(
                "LLM reply has no personal_data verdict — failing closed",
                failed=True,
                scanned=scanned,
            )
        llm_findings = [
            {
                "source": "llm",
                "kind": str(f.get("kind", "personal_data"))[:40],
                "path": str(f.get("path", ""))[:200],
                "reason": str(f.get("reason", ""))[:300],
            }
            for f in reply.get("findings") or []
            if isinstance(f, dict)
        ]
        if reply["personal_data"] or llm_findings:
            findings = llm_findings or [
                {"source": "llm", "kind": "personal_data", "path": "", "reason": "flagged"}
            ]
            return rejected(
                "personal data found by the LLM", findings, failed=False, scanned=scanned
            )
        return {
            "clean": True,
            "findings": [],
            "failed_closed": False,
            "reason": "no personal data found by rules or LLM",
            "texts_scanned": scanned,
        }
