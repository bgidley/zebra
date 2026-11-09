"""Scan a code diff before it leaves the instance as a GitHub pull request (#282, slice A).

``contribute_diff_scan`` checks the **added lines** of a unified diff, every touched path, the
commit messages, the PR title and body and the author name:

- the Commons personal-data rules (``pii_scan.rule_findings``) and confidentiality rules
  (``confidentiality.confidential_rule_findings``, without its generic URL and ``key: value``
  credential rules, which fire on ordinary code), plus ``ZEBRA_SYNC_CONFIDENTIAL_PATTERNS``;
- secret rules (token formats, armored ``-----BEGIN`` blocks, OCI ocids, AWS keys, JWTs, quoted
  secret literals, high-entropy strings);
- blocked files (env files, keys, credential directories, binaries); ``SENSITIVE_PATHS`` are only
  flagged for the owner;
- a size cap, then one low-tier LLM call for personal details the rules miss.

It **fails closed**: the route is ``clean`` only when the diff parses, no rule fires and the LLM
answers ``personal_data: false``. Anything else routes ``rejected``. Findings are masked.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.commons.confidentiality import confidential_rule_findings, configured_patterns
from zebra_tasks.commons.pii_scan import ScanText, _mask, rule_findings
from zebra_tasks.knowledge.extract import resolve_raw
from zebra_tasks.llm.base import Message
from zebra_tasks.llm.client import get_llm, model_for
from zebra_tasks.llm.structured import complete_json

logger = logging.getLogger(__name__)

ROUTE_CLEAN = "clean"
ROUTE_REJECTED = "rejected"
DEFAULT_MAX_CHARS = 100_000

# Changes here need extra owner attention, but are not refused (same list as the host builder).
SENSITIVE_PATHS = (".gitlab-ci.yml", "scripts/", "deploy/", "docker/", "Dockerfile")

# Confidentiality kinds that fire on ordinary code (``https://openrouter.ai``,
# ``api_key = os.environ[...]``, ``self.private``, ``0.0.0.0``); the secret and host rules
# below replace them.
_SKIPPED_CONFIDENTIAL_KINDS = frozenset({"url", "credential", "internal_host"})

# Lock files hold only versions, hashes and package URLs: secret rules only, and not sent to
# the LLM (four-part versions read as IP addresses).
_LOCK_FILES = frozenset(
    {"uv.lock", "poetry.lock", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "Cargo.lock"}
)

# Internal hosts as they appear in code: always for corporate suffixes, and ``.local`` /
# ``.private`` / ``.lan`` only after a scheme, ``@`` or before a port (else ``self.private``).
_CORP_HOST_RE = re.compile(
    r"\b(?:[a-z0-9-]+\.)+(?:internal|corp|intranet|home\.arpa)\b", re.IGNORECASE
)
_LOCAL_HOST_RE = re.compile(
    r"(?:://|@)(?:[a-z0-9-]+\.)+(?:local|private|lan)\b"
    r"|\b(?:[a-z0-9-]+\.)+(?:local|private|lan):\d{2,5}\b",
    re.IGNORECASE,
)
_IPV4_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")

_BLOCKED_NAMES = frozenset(
    {
        "site.env",
        ".netrc",
        ".pypirc",
        ".npmrc",
        ".pgpass",
        "credentials",
        "credentials.json",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "known_hosts",
        "authorized_keys",
    }
)
_BLOCKED_SUFFIXES = (
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".jks",
    ".keystore",
    ".kdbx",
    ".gpg",
    ".asc",
    ".ppk",
)
_BLOCKED_DIRS = frozenset(
    {".ssh", ".aws", ".oci", ".gnupg", ".kube", ".docker", "commons-keys", ".zebra-agent"}
)
_BINARY_SUFFIXES = (
    ".so",
    ".dll",
    ".dylib",
    ".exe",
    ".bin",
    ".pyc",
    ".o",
    ".a",
    ".jar",
    ".class",
    ".whl",
    ".zip",
    ".tar",
    ".gz",
    ".tgz",
    ".bz2",
    ".xz",
    ".7z",
    ".sqlite",
    ".sqlite3",
    ".db",
    ".dmp",
)

_SECRET_RES = (
    re.compile(r"\b(?:ghp|gho|ghs|ghu|ghr)_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bsk-(?:or|ant|proj)-[A-Za-z0-9_-]{8,}"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\baws_secret_access_key\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"-----BEGIN [A-Z0-9 ]+-----"),
    re.compile(r"\bnsec1[02-9ac-hj-np-z]{20,}"),
    re.compile(r"\bocid1\.(?:tenancy|user|key|credential|customersecretkey|vaultsecret)\.[\w.-]+"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    # A quoted literal assigned to a secret-looking name: password = "hunter22"
    re.compile(
        r"(?:password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|private[_-]?key)"
        r"[\"']?\s*[:=]\s*[\"'][^\"'\s{}<>$]{8,}[\"']",
        re.IGNORECASE,
    ),
)
_TOKEN_RE = re.compile(r"[A-Za-z0-9+/_-]{32,}={0,2}")
# Scheme, host and path of a URL (not its query): public links, not secrets.
_URL_PATH_RE = re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s?#'\"<>()]+", re.IGNORECASE)
ENTROPY_THRESHOLD = 4.0

# Emails a contribution is expected to carry (DCO sign-off, co-author trailers).
_ALLOWED_EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+-]+@(?:users\.)?noreply\.github\.com\b|\bnoreply@anthropic\.com\b"
)
_ISO_TIME_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?\b")
_GITHUB_LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")

_HUNK_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_DIFF_GIT_RE = re.compile(r"^diff --git a/(.*) b/(.*)$")
_HEADER_PREFIXES = (
    "index ",
    "old mode ",
    "new mode ",
    "deleted file mode ",
    "new file mode ",
    "similarity index ",
    "dissimilarity index ",
    "rename from ",
    "rename to ",
    "copy from ",
    "copy to ",
    "--- ",
    "+++ ",
)

SYSTEM_PROMPT = """You check a code change before it is published as a public pull request to \
an open-source project. Find personal data: anything that identifies or describes a specific \
real, private person or household — names, home or work addresses, contact details, account or \
ID numbers, health, financial, family, relationship or location details, private schedules, \
employer-confidential facts, credentials or secrets.

Not personal data: code, generic comments and docs, {{template}} placeholders, public \
organisations and services, public figures named only as examples, obviously fictional sample \
data (Jane Doe, example.com), and the project's own maintainers and bots in trailers.

Reply with JSON only:
{"personal_data": true|false,
 "findings": [{"path": "<path given>", "kind": "<name|contact|address|health|...>", \
"reason": "<short reason, do not repeat the data>"}]}"""


@dataclass
class DiffFile:
    """One file of a unified diff."""

    path: str
    old_path: str | None = None
    new: bool = False
    deleted: bool = False
    binary: bool = False
    added: list[tuple[int, str]] = field(default_factory=list)


@dataclass
class ParsedDiff:
    """A parsed diff: its files and any text outside the hunks."""

    files: list[DiffFile]
    loose: list[ScanText]


class DiffParseError(ValueError):
    """The diff is malformed; the scan fails closed."""


def _strip_prefix(path: str) -> str:
    path = path.strip().strip('"')
    if path.startswith(("a/", "b/")):
        return path[2:]
    return path


def parse_diff(diff: str) -> ParsedDiff:
    """Parse a unified (``git diff`` / ``format-patch``) diff.

    Hunk headers give line counts, so an added line that starts with ``+++`` is still an added
    line. Lines outside hunks that are not git headers are kept as loose text to scan.

    Raises:
        DiffParseError: A hunk runs short or a hunk has no file.
    """
    files: list[DiffFile] = []
    loose: list[ScanText] = []
    current: DiffFile | None = None
    lines = diff.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _DIFF_GIT_RE.match(line)
        if m:
            current = DiffFile(path=m.group(2), old_path=m.group(1))
            files.append(current)
            i += 1
            continue
        hunk = _HUNK_RE.match(line)
        if hunk:
            if current is None:
                raise DiffParseError(f"hunk without a file at line {i + 1}")
            old_left = int(hunk.group(1)) if hunk.group(1) is not None else 1
            new_line = int(hunk.group(2))
            new_left = int(hunk.group(3)) if hunk.group(3) is not None else 1
            i += 1
            while old_left > 0 or new_left > 0:
                if i >= len(lines):
                    raise DiffParseError(f"hunk in {current.path} ends early")
                body = lines[i]
                tag = body[:1]
                if tag == "+":
                    if new_left <= 0:
                        raise DiffParseError(f"hunk in {current.path} has too many added lines")
                    current.added.append((new_line, body[1:]))
                    new_line += 1
                    new_left -= 1
                elif tag == "-":
                    if old_left <= 0:
                        raise DiffParseError(f"hunk in {current.path} has too many removed lines")
                    old_left -= 1
                elif tag in (" ", ""):
                    if old_left <= 0 or new_left <= 0:
                        raise DiffParseError(f"hunk in {current.path} has too many lines")
                    old_left -= 1
                    new_left -= 1
                    new_line += 1
                elif tag != "\\":
                    raise DiffParseError(f"unexpected line in hunk of {current.path}")
                i += 1
            continue
        if line.startswith("--- ") and (current is None or current.added):
            # A plain unified diff without ``diff --git`` headers.
            current = DiffFile(path=_strip_prefix(line[4:]), old_path=_strip_prefix(line[4:]))
            files.append(current)
        if current is not None and line.startswith(_HEADER_PREFIXES):
            if line.startswith("+++ "):
                target = line[4:].strip()
                if target == "/dev/null":
                    current.deleted = True
                else:
                    current.path = _strip_prefix(target)
            elif line.startswith("--- ") and line[4:].strip() == "/dev/null":
                current.new = True
            elif line.startswith("new file mode "):
                current.new = True
            elif line.startswith("deleted file mode "):
                current.deleted = True
            elif line.startswith(("rename to ", "copy to ")):
                current.path = line.split(" to ", 1)[1].strip()
        elif current is not None and (
            line.startswith("Binary files ") or line.strip() == "GIT binary patch"
        ):
            current.binary = True
        elif line.strip():
            loose.append(ScanText(f"diff line {i + 1}", line))
        i += 1
    return ParsedDiff(files=files, loose=loose)


def shannon_entropy(text: str) -> float:
    """Bits per character of *text*."""
    if not text:
        return 0.0
    counts = Counter(text)
    return -sum(n / len(text) * math.log2(n / len(text)) for n in counts.values())


def _high_entropy(token: str) -> bool:
    if "/" in token:
        # A path (``openspec/changes/2026-11-03-x/…``) is not a secret; a base64 secret
        # with a ``/`` still has a long random segment.
        token = max(token.split("/"), key=len)
        if len(token) < 20:
            return False
    has_classes = (
        any(c.isupper() for c in token)
        and any(c.islower() for c in token)
        and any(c.isdigit() for c in token)
    )
    return has_classes and shannon_entropy(token) >= ENTROPY_THRESHOLD


def secret_findings(texts: list[ScanText]) -> list[dict[str, str]]:
    """Secrets the secret rules and the entropy rule find."""
    findings: list[dict[str, str]] = []
    for item in texts:
        for pattern in _SECRET_RES:
            for m in pattern.finditer(item.text):
                findings.append(
                    {"source": "rule", "kind": "secret", "path": item.path, "text": _mask(m[0])}
                )
        # Credentials in a URL's userinfo are a ``url_credentials`` finding; its query still
        # counts here (``?token=…``), its host and path do not.
        for m in _TOKEN_RE.finditer(_URL_PATH_RE.sub(" ", item.text)):
            if _high_entropy(m.group(0)):
                findings.append(
                    {
                        "source": "rule",
                        "kind": "high_entropy",
                        "path": item.path,
                        "text": _mask(m.group(0)),
                    }
                )
    return findings


def _private_ip(text: str) -> bool:
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return False
    return ip.is_private and not (ip.is_loopback or ip.is_unspecified)


def host_findings(texts: list[ScanText]) -> list[dict[str, str]]:
    """Internal hostnames and private addresses, as they appear in code."""
    findings: list[dict[str, str]] = []
    for item in texts:
        hits = [m.group(0) for m in _CORP_HOST_RE.finditer(item.text)]
        hits += [m.group(0) for m in _LOCAL_HOST_RE.finditer(item.text)]
        hits += [m.group(0) for m in _IPV4_RE.finditer(item.text) if _private_ip(m.group(0))]
        findings += [
            {"source": "rule", "kind": "internal_host", "path": item.path, "text": _mask(h)}
            for h in hits
        ]
    return findings


def blocked_reason(path: str) -> str | None:
    """Why a file may not be contributed, or None."""
    p = PurePosixPath(path)
    name = p.name.lower()
    if name.startswith(".env") or name.endswith(".env"):
        return "environment file"
    if name in _BLOCKED_NAMES or name.startswith(("id_rsa", "id_ed25519", "id_ecdsa")):
        return "credential file"
    if name.endswith(_BLOCKED_SUFFIXES):
        return "key or certificate file"
    if any(part.lower() in _BLOCKED_DIRS for part in p.parts[:-1]):
        return "credential directory"
    if name.endswith(_BINARY_SUFFIXES):
        return "binary file"
    return None


def is_lock_file(path: str) -> bool:
    """A dependency lock file: versions, hashes and package URLs only."""
    return PurePosixPath(path).name in _LOCK_FILES


def is_sensitive(path: str) -> bool:
    """CI, deploy, scripts or container files: flagged for the owner, not refused."""
    return path.startswith(SENSITIVE_PATHS)


def noreply_email(login: Any, user_id: Any = None) -> str | None:
    """The GitHub noreply address for *login* (``<id>+<login>@…`` when the id is known)."""
    if not isinstance(login, str) or not _GITHUB_LOGIN_RE.match(login):
        return None
    if isinstance(user_id, int | str) and str(user_id).isdigit():
        return f"{user_id}+{login}@users.noreply.github.com"
    return f"{login}@users.noreply.github.com"


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list | tuple):
        return [str(v) for v in value if v is not None and str(v).strip()]
    return [str(value)]


def _normalise(text: str) -> str:
    """Drop what the personal-data rules misread: noreply emails, ISO timestamps (phones)."""
    text = _ALLOWED_EMAIL_RE.sub("noreply@example.com", text)
    return _ISO_TIME_RE.sub("DATE", text)


def _dedupe(findings: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple] = set()
    out = []
    for f in findings:
        key = (f.get("kind"), f.get("path"), f.get("text"), f.get("reason"))
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


async def scan_diff(
    diff: Any,
    *,
    llm: Any,
    commit_messages: Any = None,
    pr_title: Any = None,
    pr_body: Any = None,
    author_name: Any = None,
    author_email: Any = None,
    github_login: Any = None,
    github_user_id: Any = None,
    patterns: list[str] | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> dict[str, Any]:
    """Scan a diff and its PR metadata; ``llm`` is a provider or None (fails closed).

    Returns ``{verdict, clean, findings, failed_closed, reason, files, sensitive_files,
    added_lines, diff_sha256, author_email}``.
    """
    rewritten = noreply_email(github_login, github_user_id)
    result: dict[str, Any] = {
        "verdict": ROUTE_REJECTED,
        "clean": False,
        "findings": [],
        "failed_closed": False,
        "reason": "",
        "files": [],
        "sensitive_files": [],
        "added_lines": 0,
        "diff_sha256": None,
        "author_email": rewritten,
    }

    def rejected(reason: str, findings=None, *, failed: bool) -> dict[str, Any]:
        result.update(findings=_dedupe(findings or []), failed_closed=failed, reason=reason)
        return result

    if not isinstance(diff, str) or not diff.strip():
        return rejected("no diff to scan — failing closed", failed=True)
    result["diff_sha256"] = hashlib.sha256(diff.encode("utf-8")).hexdigest()
    try:
        parsed = parse_diff(diff)
    except DiffParseError as e:
        return rejected(f"diff does not parse — failing closed: {e}", failed=True)
    if not parsed.files:
        return rejected("diff has no files — failing closed", failed=True)
    try:
        compiled = [re.compile(p, re.IGNORECASE) for p in patterns or []]
    except re.error as e:
        return rejected(f"bad confidential pattern — failing closed: {e}", failed=True)

    result["files"] = [f.path for f in parsed.files]
    result["sensitive_files"] = [f.path for f in parsed.files if is_sensitive(f.path)]
    result["added_lines"] = sum(len(f.added) for f in parsed.files)

    findings: list[dict[str, str]] = []
    for f in parsed.files:
        if f.deleted and not f.added:
            continue  # deleting a file leaks nothing
        reason = "binary file" if f.binary else blocked_reason(f.path)
        if reason:
            findings.append(
                {"source": "rule", "kind": "blocked_file", "path": f.path, "reason": reason}
            )

    # Everything that would leave the instance, besides context and removed lines.
    texts: list[ScanText] = []
    lock_lines: list[ScanText] = []
    for f in parsed.files:
        texts.append(ScanText(f"{f.path} (path)", f.path))
        if f.old_path and f.old_path != f.path:
            texts.append(ScanText(f"{f.old_path} (path)", f.old_path))
        added = [ScanText(f"{f.path}:{n}", line) for n, line in f.added if line.strip()]
        (lock_lines if is_lock_file(f.path) else texts).extend(added)
    texts.extend(parsed.loose)
    for n, message in enumerate(_as_list(commit_messages)):
        texts.append(ScanText(f"commit_message[{n}]", message))
    texts.extend(ScanText("pr_title", t) for t in _as_list(pr_title))
    texts.extend(ScanText("pr_body", t) for t in _as_list(pr_body))
    rules_only = [ScanText("author_name", t) for t in _as_list(author_name)]
    if rewritten is None:
        rules_only += [ScanText("author_email", t) for t in _as_list(author_email)]

    scanned = [ScanText(t.path, _normalise(t.text)) for t in texts + rules_only]
    findings += rule_findings(scanned)
    findings += [
        f
        for f in confidential_rule_findings(scanned, compiled)
        if f["kind"] not in _SKIPPED_CONFIDENTIAL_KINDS
    ]
    findings += host_findings(scanned)
    findings += secret_findings(scanned + lock_lines)
    if findings:
        return rejected(
            "secrets, personal data or blocked files found by rules", findings, failed=False
        )

    payload = _llm_payload(parsed, texts)
    if len(payload) > max_chars:
        return rejected(
            f"{len(payload)} characters is more than the scan limit {max_chars} — failing closed",
            failed=True,
        )
    if llm is None:
        return rejected("no LLM for the scan — failing closed", failed=True)
    try:
        reply = await complete_json(
            llm,
            [Message.system(SYSTEM_PROMPT), Message.user(payload)],
            temperature=0.0,
            max_tokens=1500,
        )
    except Exception as e:  # provider error, empty or unusable JSON
        logger.warning("Diff scan: LLM check failed (%s) — failing closed", e)
        return rejected(f"LLM check failed — failing closed: {e}", failed=True)
    if not isinstance(reply, dict) or not isinstance(reply.get("personal_data"), bool):
        return rejected("LLM reply has no personal_data verdict — failing closed", failed=True)
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
        return rejected(
            "personal data found by the LLM",
            llm_findings
            or [{"source": "llm", "kind": "personal_data", "path": "", "reason": "flagged"}],
            failed=False,
        )
    result.update(
        verdict=ROUTE_CLEAN,
        clean=True,
        reason="no secrets, personal data or blocked files found by rules or LLM",
    )
    return result


def _llm_payload(parsed: ParsedDiff, texts: list[ScanText]) -> str:
    """Added lines grouped per file, then the loose text, messages and PR text."""
    items = []
    for f in parsed.files:
        if f.added and not is_lock_file(f.path):
            items.append(
                {"path": f.path, "added": "\n".join(f"{n}: {line}" for n, line in f.added)}
            )
    file_paths = {f"{f.path}:" for f in parsed.files}
    for t in texts:
        if t.path.endswith(" (path)") or any(t.path.startswith(p) for p in file_paths):
            continue
        items.append({"path": t.path, "text": t.text})
    return json.dumps(items, ensure_ascii=False)


class ContributeDiffScanAction(TaskAction):
    """Scan a contribution's diff and PR text; route ``clean`` or ``rejected``.

    Properties:
        diff: Unified diff (template-resolved)
        commit_messages: Commit messages (list or string)
        pr_title / pr_body: The PR text
        author_name / author_email: The commit author; the email is replaced by the GitHub
            noreply address when ``github_login`` is given, else scanned like any text
        github_login / github_user_id: The contributor's GitHub account
        patterns: Extra confidential regexes; the device's ``SYNC_CONFIDENTIAL_PATTERNS``
            (``__commons_sync__``, else ``ZEBRA_SYNC_CONFIDENTIAL_PATTERNS``) always apply
        model: LLM tier (default ``low``)
        max_chars: Most text the LLM is shown; more fails closed (default 100000)
        output_key: Process property for the result (default ``diff_scan``)
    """

    description = (
        "Scan a code diff, its commit messages and PR text for secrets, personal data, "
        "confidential material and blocked files before it is proposed upstream; fails closed."
    )
    # Reads and one LLM call; nothing outside this run changes (#245 convention).
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(name="diff", type="string", description="Unified diff", required=True),
        ParameterDef(
            name="commit_messages", type="array", description="Commit messages", required=False
        ),
        ParameterDef(name="pr_title", type="string", description="PR title", required=False),
        ParameterDef(name="pr_body", type="string", description="PR body", required=False),
        ParameterDef(name="author_name", type="string", description="Author", required=False),
        ParameterDef(
            name="author_email", type="string", description="Author email", required=False
        ),
        ParameterDef(
            name="github_login", type="string", description="GitHub login", required=False
        ),
        ParameterDef(
            name="github_user_id", type="string", description="GitHub user id", required=False
        ),
        ParameterDef(name="patterns", type="array", description="Extra regexes", required=False),
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
            default="diff_scan",
        ),
    ]
    outputs = [
        ParameterDef(name="verdict", type="string", description="clean or rejected", required=True),
        ParameterDef(name="clean", type="boolean", description="Nothing found", required=True),
        ParameterDef(name="findings", type="array", description="What was found", required=True),
        ParameterDef(
            name="failed_closed",
            type="boolean",
            description="The scan could not complete and rejected",
            required=True,
        ),
        ParameterDef(
            name="author_email",
            type="string",
            description="GitHub noreply address for the commits",
            required=False,
        ),
        ParameterDef(
            name="diff_sha256", type="string", description="sha256 of the diff", required=False
        ),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Scan, store the result under ``output_key`` and route."""
        props = task.properties

        def prop(name: str) -> Any:
            return resolve_raw(context, props.get(name))

        sync = context.extras.get("__commons_sync__")
        extra = list(getattr(sync, "confidential_patterns", None) or [])
        extra += configured_patterns(prop("patterns"))
        try:
            llm = get_llm(model_for(task, context, default="low"), context)
        except Exception as e:  # no provider configured
            logger.warning("Diff scan: no LLM (%s) — failing closed", e)
            llm = None
        try:
            max_chars = int(props.get("max_chars", DEFAULT_MAX_CHARS))
        except (TypeError, ValueError):
            max_chars = DEFAULT_MAX_CHARS
        result = await scan_diff(
            prop("diff"),
            llm=llm,
            commit_messages=prop("commit_messages"),
            pr_title=prop("pr_title"),
            pr_body=prop("pr_body"),
            author_name=prop("author_name"),
            author_email=prop("author_email"),
            github_login=prop("github_login"),
            github_user_id=prop("github_user_id"),
            patterns=extra,
            max_chars=max_chars,
        )
        context.set_process_property(props.get("output_key", "diff_scan"), result)
        logger.info(
            "Diff scan: %s (%d findings%s)",
            result["verdict"],
            len(result["findings"]),
            ", failed closed" if result["failed_closed"] else "",
        )
        return TaskResult(success=True, output=result, next_route=result["verdict"])
