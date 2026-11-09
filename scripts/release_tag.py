"""Cut a semver release tag from green master, with notes from closed issues (#283).

Run by the manual ``release:tag`` CI job, which only exists on master push pipelines and sits
in the last stage, so it can only start once lint, tests, deploy and smoke are green:

    python scripts/release_tag.py --ref "$CI_COMMIT_SHA" --bump minor

It finds the newest ``vX.Y.Z`` tag, picks the next version (``--bump`` or ``--version``),
lists the issues closed by commits since that tag (``Closes #N`` / ``Fixes #N`` /
``Resolves #N``, kept only when GitLab says the issue is closed) and creates a GitLab release,
which creates the tag at ``--ref``. ``--dry-run`` prints the version and notes and changes
nothing; it works without a token (issue titles then come from the commit subjects).

Stdlib only. Token: ``RELEASE_GITLAB_TOKEN`` (a personal access token that can read issues and
the repository and create tags and releases on the project).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field

DEFAULT_API = "https://gitlab.com/api/v4"
DEFAULT_PROJECT = "gidley/zebra"
FIRST_VERSION = "0.1.0"
TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
CLOSES_RE = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+#(\d+)\b", re.I)
SECURITY_LABEL = "security"

Api = Callable[[str, str, dict | None], tuple[int, object]]


class ReleaseError(Exception):
    """A release cannot be cut; the message says why."""


# --- versions -----------------------------------------------------------------------------


def parse_version(text: str) -> tuple[int, int, int]:
    """Parse ``X.Y.Z`` or ``vX.Y.Z`` into a tuple, raising ReleaseError otherwise."""
    match = TAG_RE.match(text if text.startswith("v") else f"v{text}")
    if not match:
        raise ReleaseError(f"not a release version (X.Y.Z): {text!r}")
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


def format_version(version: tuple[int, int, int]) -> str:
    return ".".join(str(part) for part in version)


def bump(version: tuple[int, int, int], part: str) -> tuple[int, int, int]:
    """Return the next version for a ``major`` / ``minor`` / ``patch`` bump."""
    major, minor, patch = version
    if part == "major":
        return major + 1, 0, 0
    if part == "minor":
        return major, minor + 1, 0
    if part == "patch":
        return major, minor, patch + 1
    raise ReleaseError(f"unknown bump {part!r} (major, minor or patch)")


def latest_tag(tags: list[str]) -> str | None:
    """Return the highest ``vX.Y.Z`` tag, ignoring anything that is not a release tag."""
    releases = [tag for tag in tags if TAG_RE.match(tag)]
    return max(releases, key=parse_version) if releases else None


def next_version(previous: str | None, part: str, explicit: str | None) -> str:
    """Pick the version to release; it must be above the previous release."""
    if explicit:
        chosen = parse_version(explicit)
    elif previous is None:
        chosen = parse_version(FIRST_VERSION)
    else:
        chosen = bump(parse_version(previous), part)
    if previous is not None and chosen <= parse_version(previous):
        raise ReleaseError(f"version {format_version(chosen)} is not above {previous}")
    return format_version(chosen)


# --- git ------------------------------------------------------------------------------------


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def ensure_history() -> None:
    """Fetch tags, and the full history if the CI clone is shallow."""
    args = ["fetch", "--quiet", "--tags", "origin"]
    if _git("rev-parse", "--is-shallow-repository") == "true":
        args.insert(3, "--unshallow")
    _git(*args)


def release_tags(ref: str) -> list[str]:
    """Release tags reachable from ``ref``."""
    out = _git("tag", "--list", "v*", "--merged", ref)
    return [line for line in out.splitlines() if line]


@dataclass
class Commit:
    sha: str
    subject: str
    body: str


def commits_between(previous: str | None, ref: str) -> list[Commit]:
    """Commits in ``previous..ref`` (all of history before the first release)."""
    rev_range = f"{previous}..{ref}" if previous else ref
    out = _git("log", "--format=%H%x1f%s%x1f%b%x1e", rev_range)
    commits = []
    for record in out.split("\x1e"):
        record = record.strip("\n")
        if not record:
            continue
        sha, subject, body = (record.split("\x1f") + ["", ""])[:3]
        commits.append(Commit(sha=sha, subject=subject, body=body))
    return commits


# --- notes ----------------------------------------------------------------------------------


@dataclass
class Issue:
    iid: int
    title: str
    closed: bool = True
    labels: list[str] = field(default_factory=list)
    url: str = ""


def closed_issue_refs(commits: list[Commit]) -> dict[int, str]:
    """Issue numbers a commit closes, mapped to the subject of the first commit closing it."""
    refs: dict[int, str] = {}
    for commit in reversed(commits):  # oldest first, so the first closing subject wins
        for match in CLOSES_RE.finditer(f"{commit.subject}\n{commit.body}"):
            refs.setdefault(int(match.group(1)), commit.subject)
    return dict(sorted(refs.items()))


def resolve_issues(
    refs: dict[int, str], fetch: Callable[[int], Issue | None] | None
) -> list[Issue]:
    """Look each referenced issue up; keep closed ones. Without ``fetch`` keep them all."""
    issues = []
    for iid, subject in refs.items():
        issue = fetch(iid) if fetch else None
        if issue is None:
            issue = Issue(iid=iid, title=subject)
        if issue.closed:
            issues.append(issue)
    return issues


def render_notes(version: str, previous: str | None, commits: int, issues: list[Issue]) -> str:
    """Markdown release notes: security fixes first, then the other closed issues."""
    since = f"since {previous}" if previous else "(first release)"
    lines = [f"## Zebra v{version}", "", f"{commits} commits {since}.", ""]
    security = [issue for issue in issues if SECURITY_LABEL in issue.labels]
    other = [issue for issue in issues if SECURITY_LABEL not in issue.labels]
    for heading, group in (("Security", security), ("Closed issues", other)):
        if not group:
            continue
        lines += [f"### {heading}", ""]
        lines += [f"- #{issue.iid} {issue.title}" for issue in group]
        lines.append("")
    if not issues:
        lines += ["No issues closed in this release.", ""]
    return "\n".join(lines)


# --- GitLab -----------------------------------------------------------------------------------


def http_api(base: str, token: str) -> Api:
    """A tiny GitLab REST client: ``api(method, path, body) -> (status, json)``."""

    def call(method: str, path: str, body: dict | None = None) -> tuple[int, object]:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(f"{base}{path}", data=data, method=method)
        request.add_header("PRIVATE-TOKEN", token)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
                return response.status, json.loads(response.read() or b"null")
        except urllib.error.HTTPError as exc:
            return exc.code, None

    return call


def project_path(project: str) -> str:
    return f"/projects/{urllib.parse.quote(project, safe='')}"


def issue_fetcher(api: Api, project: str) -> Callable[[int], Issue | None]:
    def fetch(iid: int) -> Issue | None:
        status, data = api("GET", f"{project_path(project)}/issues/{iid}", None)
        if status != 200 or not isinstance(data, dict):
            return None
        return Issue(
            iid=iid,
            title=str(data.get("title", "")),
            closed=data.get("state") == "closed",
            labels=list(data.get("labels") or []),
            url=str(data.get("web_url", "")),
        )

    return fetch


def check_green_master(env: dict[str, str]) -> None:
    """Refuse to tag anything but a master push pipeline (the job's rules say the same)."""
    branch = env.get("CI_COMMIT_BRANCH", "")
    default = env.get("CI_DEFAULT_BRANCH", "master")
    if branch != default or env.get("CI_PIPELINE_SOURCE") != "push":
        raise ReleaseError(
            f"releases are cut only from a {default} push pipeline "
            f"(branch={branch or '-'}, source={env.get('CI_PIPELINE_SOURCE') or '-'})"
        )


def check_master_head(api: Api, project: str, ref: str, branch: str) -> None:
    """Refuse a stale pipeline: ``ref`` must still be the head of master."""
    status, data = api("GET", f"{project_path(project)}/repository/branches/{branch}", None)
    head = (data or {}).get("commit", {}).get("id") if isinstance(data, dict) else None
    if status != 200 or not head:
        raise ReleaseError(f"could not read the head of {branch} (HTTP {status})")
    if head != ref:
        raise ReleaseError(f"{ref[:12]} is no longer the head of {branch} ({head[:12]})")


def create_release(api: Api, project: str, version: str, ref: str, notes: str) -> str:
    """Create the GitLab release (and with it the tag at ``ref``); return its URL."""
    tag = f"v{version}"
    status, _ = api("GET", f"{project_path(project)}/repository/tags/{tag}", None)
    if status == 200:
        raise ReleaseError(f"tag {tag} already exists")
    body = {"name": f"Zebra {tag}", "tag_name": tag, "ref": ref, "description": notes}
    status, data = api("POST", f"{project_path(project)}/releases", body)
    if status != 201:
        raise ReleaseError(f"creating release {tag} failed (HTTP {status})")
    links = data.get("_links", {}) if isinstance(data, dict) else {}
    return str(links.get("self", tag))


# --- main ---------------------------------------------------------------------------------------


def run(
    args: argparse.Namespace,
    env: dict[str, str],
    api: Api | None,
    fetch_history: Callable[[], None] = ensure_history,
) -> str:
    """Plan (and unless ``--dry-run``, create) the release; return the notes."""
    if not args.dry_run:
        check_green_master(env)
        if api is None:
            raise ReleaseError("RELEASE_GITLAB_TOKEN is not set")
        check_master_head(api, args.project, args.ref, env.get("CI_DEFAULT_BRANCH", "master"))
    if args.fetch:
        fetch_history()
    previous = latest_tag(release_tags(args.ref))
    version = next_version(previous, args.bump, args.version)
    commits = commits_between(previous, args.ref)
    fetch = issue_fetcher(api, args.project) if api else None
    issues = resolve_issues(closed_issue_refs(commits), fetch)
    notes = render_notes(version, previous, len(commits), issues)
    if args.notes_file:
        with open(args.notes_file, "w") as handle:
            handle.write(notes)
    if args.dry_run:
        print(f"Would release v{version} at {args.ref} (previous: {previous or 'none'})")
    else:
        url = create_release(api, args.project, version, args.ref, notes)
        print(f"Released v{version} at {args.ref}: {url}")
    return notes


def build_parser(env: dict[str, str]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ref", default=env.get("CI_COMMIT_SHA", "HEAD"))
    parser.add_argument(
        "--bump", choices=["major", "minor", "patch"], default=env.get("RELEASE_BUMP") or "minor"
    )
    parser.add_argument("--version", default=env.get("RELEASE_VERSION") or None)
    parser.add_argument("--project", default=env.get("CI_PROJECT_PATH", DEFAULT_PROJECT))
    parser.add_argument("--api-url", default=env.get("CI_API_V4_URL", DEFAULT_API))
    parser.add_argument("--notes-file", default=None, help="also write the notes here")
    parser.add_argument("--dry-run", action="store_true", help="print, change nothing")
    parser.add_argument("--no-fetch", dest="fetch", action="store_false", help="skip git fetch")
    return parser


def main(argv: list[str] | None = None) -> int:
    env = dict(os.environ)
    args = build_parser(env).parse_args(argv)
    token = env.get("RELEASE_GITLAB_TOKEN", "")
    api = http_api(args.api_url, token) if token else None
    try:
        notes = run(args, env, api)
    except (ReleaseError, subprocess.CalledProcessError) as exc:
        print(f"release_tag: {exc}", file=sys.stderr)
        return 1
    print(notes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
