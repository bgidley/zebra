#!/usr/bin/env python3
"""import_github_pr.py - maintainer import of a contributed GitHub PR (#282 slice D).

Contributors' Zebras open PRs against the GitHub mirror (bgidley/zebra). The canonical repo and
its CI live on GitLab, and the GitLab shell runner executes code on the prod host, so imported
code must never reach CI unread. The import is therefore two explicit steps:

  prepare  <PR>   fetch the PR head, verify the Zebra-origin statement, re-scan the diff, create
                  a local branch fN/gh<PR>-<slug> at the PR head (contributor commits and
                  authorship untouched) and print the diff. Nothing is pushed. A review file
                  with the head sha is written for the maintainer.
  push     <PR> --reviewed-sha <sha>
                  only after the maintainer read the diff: re-checks the head and the scan,
                  then pushes the branch to GitLab (which starts CI). Refuses on any mismatch.

After a green pipeline the maintainer merges with the normal worktree recipe (`git merge --no-ff`
keeps contributor authorship) and pushes master to both remotes; GitHub then shows the PR merged.

Origin statement: the PR body carries a block written by the contributor's Zebra:

    <!-- zebra-origin
    npub: npub1...
    head: <40-hex head sha>
    sig: <128-hex BIP-340 signature>
    -->

``sig`` signs sha256("zebra-contribute-v1\\n<repo>\\n<head sha>") with the Zebra key. The
statement says which Zebra proposed the PR; it does not make the code trusted.

Diff scanner interface (slice A, ``contribute_diff_scan``): if
``zebra_tasks.contribute.diff_scan.scan_diff_text(patch, *, paths, commit_messages,
author_emails, pr_body)`` exists it is used and must return ``{"verdict": "clean"|"rejected",
"findings": [...]}``. Until then a conservative built-in scan runs (pii rules on added lines,
blocked paths). Either way the scan fails closed.

Usage:
  uv run python scripts/import_github_pr.py prepare <PR> [--slug words] [--allow-unsigned]
  uv run python scripts/import_github_pr.py push <PR> --reviewed-sha <sha> [--allow-unsigned]
  uv run python scripts/import_github_pr.py reject <PR> --reason "..."   (closes with a comment)

Env: GITHUB_PR_REPO (default bgidley/zebra), ZEBRA_IMPORT_GITHUB_REMOTE (github),
ZEBRA_IMPORT_GITLAB_REMOTE (origin), ZEBRA_IMPORT_MAX_DIFF_BYTES (1000000).
Exit: 0 ok, 2 refused (unsigned, bad signature, scan rejected, mismatch), 1 error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

REPO = os.environ.get("GITHUB_PR_REPO", "bgidley/zebra")
GITHUB_REMOTE = os.environ.get("ZEBRA_IMPORT_GITHUB_REMOTE", "github")
GITLAB_REMOTE = os.environ.get("ZEBRA_IMPORT_GITLAB_REMOTE", "origin")
MAX_DIFF_BYTES = int(os.environ.get("ZEBRA_IMPORT_MAX_DIFF_BYTES", "1000000"))
MESSAGE_TAG = "zebra-contribute-v1"
SENSITIVE_PATHS = (".gitlab-ci.yml", "scripts/", "deploy/", "docker/", "Dockerfile")
BLOCKED_PATH_RES = (
    re.compile(r"(^|/)\.env(\..*)?$"),
    re.compile(r"\.(pem|key|p12|pfx)$"),
    re.compile(r"(^|/)site\.env$"),
)

_ORIGIN_RE = re.compile(r"<!--\s*zebra-origin\s*(.*?)-->", re.DOTALL)
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SIG_RE = re.compile(r"^[0-9a-f]{128}$")

Runner = Callable[[list[str]], str]


class Refused(Exception):
    """The import must not proceed (exit 2)."""


@dataclass
class Origin:
    npub: str
    head: str
    sig: str


@dataclass
class PullRequest:
    number: int
    title: str
    body: str
    state: str
    author: str
    head_sha: str


@dataclass
class Scan:
    verdict: str
    findings: list[dict] = field(default_factory=list)


def run(cmd: list[str]) -> str:
    """Run a command, return stdout; raise RuntimeError with stderr on failure."""
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:3])} failed: {proc.stderr.strip()}")
    return proc.stdout


# ---------------------------------------------------------------- origin statement


def origin_message(repo: str, head_sha: str) -> bytes:
    """The 32-byte message a Zebra signs to claim a PR head."""
    return hashlib.sha256(f"{MESSAGE_TAG}\n{repo}\n{head_sha}".encode()).digest()


def parse_origin(body: str) -> Origin | None:
    """The zebra-origin block of a PR body, or None when absent or malformed."""
    match = _ORIGIN_RE.search(body or "")
    if not match:
        return None
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    if not {"npub", "head", "sig"} <= fields.keys():
        return None
    return Origin(fields["npub"], fields["head"], fields["sig"])


def verify_origin(body: str, head_sha: str, repo: str = REPO) -> Origin:
    """Check the statement signs this repo and head. Raises Refused with the reason."""
    from zebra_agent.commons import keys

    origin = parse_origin(body)
    if origin is None:
        raise Refused("no zebra-origin statement in the PR body")
    if not _SHA_RE.match(origin.head) or not _SIG_RE.match(origin.sig):
        raise Refused("zebra-origin statement is malformed")
    if origin.head != head_sha:
        raise Refused("zebra-origin signs a different head than the PR head (pushed after signing)")
    try:
        pubkey = keys.npub_decode(origin.npub)
    except (keys.InvalidKeyError, ValueError) as exc:
        raise Refused(f"zebra-origin npub is invalid: {exc}") from exc
    if not keys.verify(pubkey, origin_message(repo, head_sha), origin.sig):
        raise Refused("zebra-origin signature does not verify")
    return origin


# ---------------------------------------------------------------- diff scan


def added_lines(patch: str) -> str:
    """Only the added lines of a unified diff (what the contributor introduces)."""
    return "\n".join(
        line[1:]
        for line in patch.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


def builtin_scan(
    patch: str,
    *,
    paths: list[str],
    commit_messages: list[str],
    author_emails: list[str],
    pr_body: str,
) -> Scan:
    """Conservative fallback scan: pii/secret rules on added text, blocked paths, size cap."""
    from zebra_tasks.commons.pii_scan import ScanText, rule_findings

    findings: list[dict] = []
    if len(patch.encode()) > MAX_DIFF_BYTES:
        findings.append({"source": "size", "kind": "too_large", "path": "", "text": ""})
    for path in paths:
        if any(r.search(path) for r in BLOCKED_PATH_RES):
            findings.append({"source": "path", "kind": "blocked_path", "path": path, "text": ""})
        elif path.startswith(SENSITIVE_PATHS):
            findings.append({"source": "path", "kind": "sensitive_path", "path": path, "text": ""})
    if re.search(r"^Binary files .* differ$|^GIT binary patch$", patch, re.MULTILINE):
        findings.append({"source": "path", "kind": "binary", "path": "", "text": ""})
    texts = [
        ScanText("diff", added_lines(patch)),
        ScanText("pr_body", _ORIGIN_RE.sub("", pr_body or "")),
        *[ScanText(f"commit_message[{i}]", m) for i, m in enumerate(commit_messages)],
    ]
    findings.extend(rule_findings(texts))
    return Scan("rejected" if findings else "clean", findings)


def scan_diff(
    patch: str,
    *,
    paths: list[str],
    commit_messages: list[str],
    author_emails: list[str],
    pr_body: str,
) -> Scan:
    """Slice A's scanner when merged, else the built-in one. Fails closed on any error."""
    kwargs = dict(
        paths=paths, commit_messages=commit_messages, author_emails=author_emails, pr_body=pr_body
    )
    try:
        from zebra_tasks.contribute.diff_scan import (
            scan_diff_text,  # type: ignore[import-not-found]
        )
    except ImportError:
        scanner = builtin_scan
    else:
        scanner = scan_diff_text
    try:
        result = scanner(patch, **kwargs)
    except Exception as exc:  # noqa: BLE001 - a failed scan must reject, never pass
        return Scan(
            "rejected", [{"source": "scanner", "kind": "error", "path": "", "text": str(exc)}]
        )
    if isinstance(result, Scan):
        return result
    verdict = result.get("verdict") if isinstance(result, dict) else None
    if verdict not in ("clean", "rejected"):
        return Scan(
            "rejected", [{"source": "scanner", "kind": "bad_verdict", "path": "", "text": ""}]
        )
    return Scan(verdict, list(result.get("findings", [])))


# ---------------------------------------------------------------- git / gh steps


def fetch_pr(number: int, runner: Runner = run) -> PullRequest:
    """PR metadata from GitHub (read-only)."""
    data = json.loads(runner(["gh", "api", f"repos/{REPO}/pulls/{number}"]))
    return PullRequest(
        number=number,
        title=data["title"],
        body=data.get("body") or "",
        state=data["state"],
        author=data["user"]["login"],
        head_sha=data["head"]["sha"],
    )


def fetch_head(number: int, runner: Runner = run) -> str:
    """Fetch the PR head into the local object store; returns the fetched sha."""
    runner(["git", "fetch", GITHUB_REMOTE, f"pull/{number}/head"])
    return runner(["git", "rev-parse", "FETCH_HEAD"]).strip()


def collect_diff(head_sha: str, base: str, runner: Runner = run) -> dict:
    """Patch, paths, commit messages and author emails of base..head."""
    merge_base = runner(["git", "merge-base", base, head_sha]).strip()
    rng = f"{merge_base}..{head_sha}"
    patch = runner(["git", "diff", "--binary", rng])
    paths = [p for p in runner(["git", "diff", "--name-only", rng]).splitlines() if p]
    messages = [
        m for m in runner(["git", "log", "--format=%B%x00", rng]).split("\x00") if m.strip()
    ]
    emails = sorted(set(runner(["git", "log", "--format=%ae%n%ce", rng]).split()))
    return {"patch": patch, "paths": paths, "commit_messages": messages, "author_emails": emails}


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "change"


def branch_name(number: int, slug: str) -> str:
    return f"f{number}/gh{number}-{slugify(slug)}"


def assess(
    number: int, *, allow_unsigned: bool, runner: Runner = run
) -> tuple[PullRequest, dict, Scan]:
    """Fetch, verify head and origin, scan. Raises Refused when the import must stop."""
    pr = fetch_pr(number, runner)
    if pr.state != "open":
        raise Refused(f"PR #{number} is {pr.state}, not open")
    fetched = fetch_head(number, runner)
    if fetched != pr.head_sha:
        raise Refused("fetched head differs from the API head (PR moved while importing)")
    try:
        origin = verify_origin(pr.body, pr.head_sha)
        print(f"origin: signed by {origin.npub}")
    except Refused as exc:
        if not allow_unsigned:
            raise
        print(f"origin: UNVERIFIED ({exc}); continuing because --allow-unsigned")
    diff = collect_diff(pr.head_sha, f"{GITLAB_REMOTE}/master", runner)
    scan = scan_diff(
        diff["patch"],
        paths=diff["paths"],
        commit_messages=diff["commit_messages"],
        author_emails=diff["author_emails"],
        pr_body=pr.body,
    )
    return pr, diff, scan


def print_scan(scan: Scan) -> None:
    print(f"scan: {scan.verdict}")
    for f in scan.findings:
        print(f"  - {f.get('source')}/{f.get('kind')} {f.get('path', '')} {f.get('text', '')}")


def cmd_prepare(args: argparse.Namespace, runner: Runner = run) -> int:
    pr, diff, scan = assess(args.pr, allow_unsigned=args.allow_unsigned, runner=runner)
    print_scan(scan)
    if scan.verdict != "clean":
        raise Refused("diff scan rejected the PR; nothing created. Close it with `reject`.")
    branch = branch_name(pr.number, args.slug or pr.title)
    runner(["git", "branch", branch, pr.head_sha])
    review = Path(os.environ.get("TMPDIR", "/tmp")) / f"gh-pr-{pr.number}-review.diff"
    review.write_text(diff["patch"])
    print(f"\nPR #{pr.number} by {pr.author}: {pr.title}")
    print(f"local branch {branch} at {pr.head_sha} (NOT pushed; no CI has run)")
    print(f"full diff saved to {review}")
    print(runner(["git", "diff", "--stat", f"{GITLAB_REMOTE}/master...{pr.head_sha}"]))
    sensitive = [p for p in diff["paths"] if p.startswith(SENSITIVE_PATHS)]
    if sensitive:
        print(f"WARNING: touches CI/deploy paths the runner executes: {', '.join(sensitive)}")
    print(
        "READ THE WHOLE DIFF before pushing: the GitLab runner executes it on the prod host.\n"
        f"Then: scripts/import_github_pr.py push {pr.number} --reviewed-sha {pr.head_sha}"
    )
    return 0


def cmd_push(args: argparse.Namespace, runner: Runner = run) -> int:
    pr, _diff, scan = assess(args.pr, allow_unsigned=args.allow_unsigned, runner=runner)
    if args.reviewed_sha != pr.head_sha:
        raise Refused(
            f"reviewed sha {args.reviewed_sha} is not the PR head {pr.head_sha}; "
            "the PR changed since the diff was read, review it again with `prepare`"
        )
    print_scan(scan)
    if scan.verdict != "clean":
        raise Refused("diff scan rejected the PR; not pushing")
    branch = branch_name(pr.number, args.slug or pr.title)
    runner(["git", "push", GITLAB_REMOTE, f"{pr.head_sha}:refs/heads/{branch}"])
    print(f"pushed {branch} to {GITLAB_REMOTE}; GitLab CI starts now. Merge --no-ff when green.")
    return 0


def cmd_reject(args: argparse.Namespace, runner: Runner = run) -> int:
    runner(["gh", "pr", "close", str(args.pr), "--repo", REPO, "--comment", args.reason])
    print(f"closed PR #{args.pr} with a comment")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("prepare", "push"):
        p = sub.add_parser(name)
        p.add_argument("pr", type=int)
        p.add_argument("--slug")
        p.add_argument("--allow-unsigned", action="store_true")
        if name == "push":
            p.add_argument("--reviewed-sha", required=True)
    rej = sub.add_parser("reject")
    rej.add_argument("pr", type=int)
    rej.add_argument("--reason", required=True)
    args = parser.parse_args(argv)
    handler = {"prepare": cmd_prepare, "push": cmd_push, "reject": cmd_reject}[args.cmd]
    try:
        return handler(args)
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    except (RuntimeError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
