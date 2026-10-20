"""Zebra host builder: run Claude Code builds in a podman sandbox (#98, #172).

Runs on the prod host as ``opc`` (``zebra-builder.service``), outside Zebra's containers, so a
build never sees Zebra's secrets. Zebra writes jobs into a spool directory shared with its
containers; this service validates each job against the capability ceilings, runs headless
Claude Code in a throwaway sandbox container, and writes the result back. After a human approves
the result, it pushes the patch to a ``zebra-build/<id>`` branch and opens a draft merge request.

The sandbox is untrusted. The host never runs git (or anything else) in a workspace a sandbox
has written to, and reads sandbox outputs only as plain files: no symlinks, size-capped.

Spool layout (one directory per job, all writes are temp file + rename)::

    <spool>/<job_id>/job.json        Zebra:   the build request
    <spool>/<job_id>/status.json     builder: {state, started_at, container, ...}
    <spool>/<job_id>/result.json     builder: final build result
    <spool>/<job_id>/publish.json    Zebra:   publish request, after human approval
    <spool>/<job_id>/published.json  builder: {branch, mr_url} or {error}
    <spool>/<job_id>/cancel          Zebra:   the goal ended, stop the build
    <spool>/audit.jsonl              builder: rejections, overruns, cancels, publishes

Stdlib only. Run with ``uv run --no-project --python 3.12 scripts/zebra_builder.py``.
Design: specs/claude-code-builder-design.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import signal
import stat
import subprocess
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger("zebra_builder")

JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")
REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*(/[A-Za-z0-9][A-Za-z0-9_.-]*)+$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$")

LIVE_STATES = {"queued", "running"}
TERMINAL_STATES = {"done", "failed", "over_budget", "rejected", "cancelled"}

MAX_PROMPT_CHARS = 50_000
MAX_TITLE_CHARS = 200
MAX_TEST_COMMAND_CHARS = 1_000
PATCH_CAP_BYTES = 5_000_000
TEXT_CAP_BYTES = 1_000_000
PATCH_EXCERPT_CHARS = 60_000
LOG_TAIL_CHARS = 4_000
SUMMARY_CHARS = 4_000

# Paths whose changes run code on the host when the branch's GitLab pipeline starts (the
# runner is a shell executor on the prod host). Flagged for the reviewer, not blocked.
SENSITIVE_PATHS = (".gitlab-ci.yml", "scripts/", "deploy/", "docker/", "Dockerfile")

PREAMBLE = """\
You are Claude Code, working for Zebra on a build job.
/workspace is a git clone of {repo} at branch {base_branch}. Make the change described below.

- Work only inside /workspace. You have no credentials for pushing; do not try.
- Commit your work with clear messages as you go. Anything left uncommitted is committed
  for you at the end.
- Run the relevant tests and fix what you break.
- Finish with a short summary: what you changed, how you tested it, anything left undone.

## Job: {title}

"""

Runner = Callable[..., subprocess.CompletedProcess]


def _now() -> float:
    return time.time()


def _iso(ts: float | None = None) -> str:
    return datetime.fromtimestamp(ts if ts is not None else _now(), UTC).isoformat()


def default_runner(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float | None = 600,
) -> subprocess.CompletedProcess:
    """Run a command without a shell and capture its output."""
    return subprocess.run(
        list(args),
        cwd=cwd,
        env=dict(env) if env is not None else None,
        timeout=timeout,
        capture_output=True,
        text=True,
        check=False,
    )


@dataclass(frozen=True)
class Config:
    """Builder settings and capability ceilings (from ``builder.env``)."""

    spool: Path
    repos: tuple[str, ...] = ("gidley/zebra",)
    max_turns: int = 200
    max_minutes: int = 90
    memory: str = "3g"
    cpus: str = ""  # needs the cpu cgroup controller delegated to the user; off by default
    pids: int = 512
    image: str = "localhost/zebra-builder-sandbox:prod"
    git_host: str = "gitlab.com"
    prune_days: int = 7
    token: str = ""

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Config:
        default_spool = Path(env.get("HOME", "~")) / ".local/share/zebra/builds"
        repos = tuple(
            r.strip()
            for r in env.get("ZEBRA_BUILDER_REPOS", "gidley/zebra").split(",")
            if r.strip()
        )
        return cls(
            spool=Path(env.get("ZEBRA_BUILDER_SPOOL", str(default_spool))).expanduser(),
            repos=repos,
            max_turns=int(env.get("ZEBRA_BUILDER_MAX_TURNS", "200")),
            max_minutes=int(env.get("ZEBRA_BUILDER_MAX_MINUTES", "90")),
            memory=env.get("ZEBRA_BUILDER_MEMORY", "3g"),
            cpus=env.get("ZEBRA_BUILDER_CPUS", ""),
            pids=int(env.get("ZEBRA_BUILDER_PIDS", "512")),
            image=env.get("ZEBRA_BUILDER_IMAGE", "localhost/zebra-builder-sandbox:prod"),
            git_host=env.get("ZEBRA_BUILDER_GIT_HOST", "gitlab.com"),
            prune_days=int(env.get("ZEBRA_BUILDER_PRUNE_DAYS", "7")),
            token=env.get("CLAUDE_CODE_OAUTH_TOKEN", ""),
        )


# --------------------------------------------------------------------------- files


def write_json(path: Path, data: dict) -> None:
    """Write JSON atomically (temp file in the same directory, then rename)."""
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    os.replace(tmp, path)


def read_json(path: Path) -> dict | None:
    """Read a spool JSON file written by Zebra or the builder; None if absent or invalid."""
    text = read_output(path, TEXT_CAP_BYTES)
    if text is None:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def read_output(path: Path, cap: int) -> str | None:
    """Read a file the sandbox may have written, without trusting it.

    Refuses symlinks (``O_NOFOLLOW``), anything that is not a regular file, and files larger
    than *cap* bytes. Returns None in each of those cases.
    """
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > cap:
            return None
        chunks = []
        remaining = cap + 1
        while remaining > 0:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > cap:
            return None
        return data.decode("utf-8", errors="replace")
    finally:
        os.close(fd)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def tail(text: str | None, chars: int) -> str:
    if not text:
        return ""
    return text if len(text) <= chars else "…" + text[-chars:]


def sensitive_files(diffstat: str) -> list[str]:
    """Files in a ``git diff --stat`` that touch CI / deploy paths."""
    hits = []
    for line in diffstat.splitlines():
        name = line.split("|", 1)[0].strip()
        if "|" in line and name.startswith(SENSITIVE_PATHS):
            hits.append(name)
    return hits


# --------------------------------------------------------------------------- validation


def validate_job(job: dict, config: Config) -> tuple[str | None, list[dict]]:
    """Check a build job against its schema and the capability ceilings.

    Returns:
        ``(error, violations)``: *error* names a malformed field; *violations* lists each
        capability the job asks for beyond what the builder allows. Either one rejects the job.
    """
    if job.get("kind") != "build":
        return "kind must be 'build'", []
    repo = job.get("repo")
    if not isinstance(repo, str) or not REPO_RE.match(repo) or ".." in repo:
        return "repo must look like 'group/project'", []
    branch = job.get("base_branch")
    if not isinstance(branch, str) or not BRANCH_RE.match(branch) or ".." in branch:
        return "base_branch is not a valid branch name", []
    title = job.get("title")
    if not isinstance(title, str) or not title.strip() or len(title) > MAX_TITLE_CHARS:
        return f"title must be 1-{MAX_TITLE_CHARS} characters", []
    prompt = job.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT_CHARS:
        return f"prompt must be 1-{MAX_PROMPT_CHARS} characters", []
    test_command = job.get("test_command") or ""
    if not isinstance(test_command, str) or len(test_command) > MAX_TEST_COMMAND_CHARS:
        return f"test_command must be at most {MAX_TEST_COMMAND_CHARS} characters", []
    budget = job.get("budget")
    if not isinstance(budget, dict):
        return "budget must be an object with max_turns and minutes", []

    violations: list[dict] = []
    if repo not in config.repos:
        violations.append({"limit": "repo", "requested": repo, "allowed": list(config.repos)})
    for key, ceiling in (("max_turns", config.max_turns), ("minutes", config.max_minutes)):
        value = budget.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            return f"budget.{key} must be a positive integer", []
        if value > ceiling:
            violations.append({"limit": key, "requested": value, "allowed": ceiling})
    return None, violations


# --------------------------------------------------------------------------- builder


class Builder:
    """Process the spool: start, supervise, collect and publish builds. Stateless across runs.

    Everything the builder knows lives in the spool and in podman, so a restarted builder picks
    up running sandboxes where it left off.
    """

    def __init__(self, config: Config, runner: Runner = default_runner) -> None:
        self.config = config
        self.run = runner

    # ---- spool helpers

    def job_dirs(self) -> list[Path]:
        if not self.config.spool.is_dir():
            return []
        dirs = [
            p
            for p in self.config.spool.iterdir()
            if JOB_ID_RE.match(p.name) and p.is_dir() and not p.is_symlink()
        ]
        return sorted(dirs, key=lambda p: p.stat().st_mtime)

    def audit(self, job_id: str, event: str, **detail) -> None:
        line = json.dumps({"at": _iso(), "job_id": job_id, "event": event, **detail})
        with open(self.config.spool / "audit.jsonl", "a") as fh:
            fh.write(line + "\n")
        logger.info("audit %s %s %s", job_id[:12], event, detail)

    def finish(self, job_dir: Path, result: dict) -> None:
        """Write the final result and status for a job."""
        result.setdefault("job_id", job_dir.name)
        result.setdefault("violations", [])
        result["finished_at"] = _iso()
        write_json(job_dir / "result.json", result)
        status = read_json(job_dir / "status.json") or {}
        status.update(state=result["state"], finished_at=result["finished_at"])
        write_json(job_dir / "status.json", status)

    @staticmethod
    def container_name(job_id: str) -> str:
        return f"zebra-build-{job_id[:12]}"

    def clone_url(self, repo: str) -> str:
        return f"https://{self.config.git_host}/{repo}.git"

    # ---- main loop

    def tick(self) -> None:
        """One pass over the spool."""
        running = None
        for job_dir in self.job_dirs():
            status = read_json(job_dir / "status.json") or {}
            state = status.get("state")
            try:
                if state == "running":
                    if not self.supervise(job_dir, status):
                        running = job_dir
                elif state in (None, "queued"):
                    if (job_dir / "cancel").exists():
                        self.finish(job_dir, {"state": "cancelled", "error": "cancelled"})
                        self.audit(job_dir.name, "cancelled", before="start")
                    elif running is None:
                        if self.start(job_dir):
                            running = job_dir
                    elif state is None:
                        write_json(job_dir / "status.json", {"state": "queued"})
                elif state == "done":
                    if (job_dir / "publish.json").exists() and not (
                        job_dir / "published.json"
                    ).exists():
                        self.publish(job_dir)
            except Exception as exc:  # one bad job must not stop the others
                logger.exception("job %s failed", job_dir.name)
                self.cleanup_container(job_dir.name)
                if state != "done":
                    self.finish(job_dir, {"state": "failed", "error": f"builder error: {exc}"})
                    self.audit(job_dir.name, "failed", error=str(exc))
        self.prune()

    # ---- start

    def start(self, job_dir: Path) -> bool:
        """Validate and start a queued job. Returns True if a sandbox is now running."""
        job_id = job_dir.name
        job = read_json(job_dir / "job.json")
        if job is None:
            return False  # not fully written yet, or unreadable: leave it
        error, violations = validate_job(job, self.config)
        if error or violations:
            self.finish(
                job_dir,
                {
                    "state": "rejected",
                    "error": error or "over capability ceiling",
                    "violations": violations,
                },
            )
            self.audit(job_id, "rejected", error=error, violations=violations)
            return False
        if not self.config.token:
            self.finish(
                job_dir,
                {
                    "state": "failed",
                    "error": "No Claude Code token configured (CLAUDE_CODE_OAUTH_TOKEN)",
                },
            )
            self.audit(job_id, "failed", error="no token")
            return False

        workspace = job_dir / "workspace"
        out = job_dir / "sandbox"
        shutil.rmtree(workspace, ignore_errors=True)
        shutil.rmtree(out, ignore_errors=True)
        out.mkdir()

        clone = self.run(
            [
                "git",
                "clone",
                "--quiet",
                "--branch",
                job["base_branch"],
                "--single-branch",
                self.clone_url(job["repo"]),
                str(workspace),
            ],
            timeout=600,
        )
        if clone.returncode != 0:
            self.finish(
                job_dir, {"state": "failed", "error": f"clone failed: {tail(clone.stderr, 500)}"}
            )
            return False
        head = self.run(["git", "-C", str(workspace), "rev-parse", "HEAD"], timeout=30)
        base_sha = head.stdout.strip()
        if head.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", base_sha):
            self.finish(job_dir, {"state": "failed", "error": "could not read base commit"})
            return False

        prompt = (
            PREAMBLE.format(repo=job["repo"], base_branch=job["base_branch"], title=job["title"])
            + job["prompt"]
        )
        (out / "prompt.md").write_text(prompt)

        name = self.container_name(job_id)
        self.run(["podman", "rm", "-f", name], timeout=60)
        cmd = self.sandbox_command(job_id, job, name, workspace, out, base_sha)
        env = {**os.environ, "CLAUDE_CODE_OAUTH_TOKEN": self.config.token}
        started = self.run(cmd, env=env, timeout=120)
        if started.returncode != 0:
            self.finish(
                job_dir,
                {"state": "failed", "error": f"sandbox start failed: {tail(started.stderr, 500)}"},
            )
            return False
        write_json(
            job_dir / "status.json",
            {"state": "running", "started_at": _now(), "container": name, "base_sha": base_sha},
        )
        logger.info("job %s started in %s", job_id[:12], name)
        return True

    def sandbox_command(
        self,
        job_id: str,
        job: dict,
        name: str,
        workspace: Path,
        out: Path,
        base_sha: str,
        entrypoint: str | None = None,
    ) -> list[str]:
        """The ``podman run`` command for a build sandbox.

        Only the Claude token and the job's own parameters go into the environment; the token is
        passed by name so it never appears in the process list. The host delegates only the memory
        and pids cgroup controllers to rootless podman, so CPU is bounded by priority (``nice``)
        unless ``ZEBRA_BUILDER_CPUS`` is set on a host that delegates ``cpu`` too.
        """
        uid, gid = os.getuid(), os.getgid()
        return [
            "nice", "-n", "10", "podman", "run", "--detach", "--name", name,
            "--label", f"zebra.build={job_id}",
            "--userns=keep-id", f"--user={uid}:{gid}",
            f"--memory={self.config.memory}", f"--memory-swap={self.config.memory}",
            *([f"--cpus={self.config.cpus}"] if self.config.cpus else []),
            f"--pids-limit={self.config.pids}",
            "--cap-drop=all", "--security-opt=no-new-privileges",
            "-v", f"{workspace}:/workspace:Z",
            "-v", f"{out}:/out:Z",
            "-e", "CLAUDE_CODE_OAUTH_TOKEN",
            "-e", "HOME=/tmp/home",
            "-e", f"MAX_TURNS={job['budget']['max_turns']}",
            "-e", f"BASE_SHA={base_sha}",
            "-e", f"BUILD_TITLE={job['title']}",
            "-e", f"TEST_COMMAND={job.get('test_command') or ''}",
            *(["--entrypoint", entrypoint] if entrypoint else []),
            self.config.image,
        ]  # fmt: skip

    # ---- supervise

    def supervise(self, job_dir: Path, status: dict) -> bool:
        """Check a running job. Returns True once it is no longer running."""
        job_id = job_dir.name
        name = status.get("container") or self.container_name(job_id)
        job = read_json(job_dir / "job.json") or {}
        minutes = (job.get("budget") or {}).get("minutes", self.config.max_minutes)

        inspect = self.run(
            ["podman", "inspect", "--format", "{{.State.Status}} {{.State.ExitCode}}", name],
            timeout=30,
        )
        if inspect.returncode != 0:
            self.finish(
                job_dir,
                {"state": "failed", "error": "the sandbox container is gone (builder restarted?)"},
            )
            self.audit(job_id, "failed", error="container gone")
            return True
        container_state, _, exit_code = inspect.stdout.strip().partition(" ")

        if (job_dir / "cancel").exists():
            self.cleanup_container(job_id)
            self.remove_workspace(job_dir)
            self.finish(job_dir, {"state": "cancelled", "error": "cancelled: the goal ended"})
            self.audit(job_id, "cancelled", before="finish")
            return True

        elapsed = _now() - float(status.get("started_at", _now()))
        if container_state == "running":
            if elapsed > minutes * 60:
                self.cleanup_container(job_id)
                result = self.collect(job_dir, status, exit_code=None)
                violation = {"limit": "minutes", "used": round(elapsed / 60, 1), "allowed": minutes}
                result.update(state="over_budget", error=f"stopped after {minutes} minutes")
                result["violations"].append(violation)
                self.finish(job_dir, result)
                self.audit(job_id, "over_budget", **violation)
                return True
            return False

        result = self.collect(job_dir, status, exit_code=exit_code)
        self.cleanup_container(job_id)
        self.finish(job_dir, result)
        if result["state"] == "over_budget":
            for violation in result["violations"]:
                self.audit(job_id, "over_budget", **violation)
        return True

    def collect(self, job_dir: Path, status: dict, exit_code: str | None) -> dict:
        """Read a finished sandbox's outputs into a result, and keep a host copy of the patch."""
        out = job_dir / "sandbox"
        job = read_json(job_dir / "job.json") or {}
        claude_text = read_output(out / "claude.json", TEXT_CAP_BYTES)
        try:
            claude = json.loads(claude_text) if claude_text else {}
        except json.JSONDecodeError:
            claude = {}
        if not isinstance(claude, dict):
            claude = {}
        patch = read_output(out / "changes.patch", PATCH_CAP_BYTES) or ""
        diffstat = read_output(out / "diffstat.txt", TEXT_CAP_BYTES) or ""
        test_rc_text = (read_output(out / "test.rc", 100) or "").strip()
        test_log = read_output(out / "test.log", TEXT_CAP_BYTES)
        claude_err = read_output(out / "claude.err", TEXT_CAP_BYTES)

        if patch:
            (job_dir / "changes.patch").write_text(patch)  # host copy for publish
        redact = self.redact
        self.remove_workspace(job_dir)

        result: dict = {
            "state": "done",
            "repo": job.get("repo"),
            "base_branch": job.get("base_branch"),
            "base_sha": status.get("base_sha"),
            "title": job.get("title"),
            "summary": redact(tail(str(claude.get("result") or ""), SUMMARY_CHARS)),
            "diffstat": tail(diffstat, LOG_TAIL_CHARS),
            "sensitive_files": sensitive_files(diffstat),
            "patch_excerpt": patch[:PATCH_EXCERPT_CHARS],
            "patch_truncated": len(patch) > PATCH_EXCERPT_CHARS,
            "patch_bytes": len(patch.encode()),
            "patch_sha256": sha256(patch) if patch else None,
            "test": {
                "command": job.get("test_command") or "",
                "rc": int(test_rc_text) if test_rc_text.lstrip("-").isdigit() else None,
                "log_tail": redact(tail(test_log, LOG_TAIL_CHARS)),
            },
            "turns": claude.get("num_turns"),
            "notional_cost_usd": claude.get("total_cost_usd"),
            "duration_s": round(_now() - float(status.get("started_at", _now()))),
            "exit_code": exit_code,
            "violations": [],
        }
        max_turns = (job.get("budget") or {}).get("max_turns")
        if claude.get("subtype") == "error_max_turns":
            result.update(state="over_budget", error=f"stopped after {max_turns} turns")
            result["violations"].append(
                {"limit": "max_turns", "used": claude.get("num_turns"), "allowed": max_turns}
            )
        elif not claude or claude.get("is_error"):
            result.update(
                state="failed",
                error="Claude Code did not finish cleanly: "
                + (
                    redact(tail(str(claude.get("result") or ""), 500))
                    or redact(tail(claude_err, 500))
                    or "no result"
                ),
            )
        elif not patch:
            result.update(state="failed", error="Claude Code made no changes")
        elif self.config.token and self.config.token in patch:
            result.update(
                state="failed", error="the patch contains the Claude token; refusing to keep it"
            )
            result["patch_excerpt"] = ""
            (job_dir / "changes.patch").unlink(missing_ok=True)
        return result

    def redact(self, text: str) -> str:
        """Remove the Claude token from text the sandbox produced before it leaves the host."""
        return text.replace(self.config.token, "[REDACTED]") if self.config.token else text

    def cleanup_container(self, job_id: str) -> None:
        self.run(["podman", "rm", "-f", "-t", "10", self.container_name(job_id)], timeout=120)

    @staticmethod
    def remove_workspace(job_dir: Path) -> None:
        # rmtree never follows symlinks, so a hostile workspace cannot redirect it.
        shutil.rmtree(job_dir / "workspace", ignore_errors=True)
        shutil.rmtree(job_dir / "sandbox", ignore_errors=True)

    # ---- publish

    def publish(self, job_dir: Path) -> None:
        """Push an approved build to ``zebra-build/<id>`` and open a draft MR."""
        job_id = job_dir.name
        job = read_json(job_dir / "job.json") or {}
        result = read_json(job_dir / "result.json") or {}
        request = read_json(job_dir / "publish.json") or {}
        repo, base_branch = job.get("repo"), job.get("base_branch")
        base_sha = result.get("base_sha") or ""
        branch = f"zebra-build/{job_id[:12]}"

        def fail(error: str) -> None:
            write_json(job_dir / "published.json", {"error": error, "at": _iso()})
            self.audit(job_id, "publish_failed", error=error)

        error, _ = validate_job(job, self.config)
        if error or repo not in self.config.repos:
            return fail(f"job is not publishable: {error or 'repo not allowlisted'}")
        if not re.fullmatch(r"[0-9a-f]{40}", base_sha):
            return fail("result has no base commit")
        patch = job_dir / "changes.patch"
        patch_text = read_output(patch, PATCH_CAP_BYTES)
        if patch_text is None:
            return fail("no patch to publish")
        if request.get("patch_sha256") != sha256(patch_text):
            return fail("the approved patch does not match the built patch")

        clone = job_dir / "publish"
        shutil.rmtree(clone, ignore_errors=True)
        git = ["git", "-C", str(clone), "-c", "core.hooksPath=/dev/null"]
        steps = [
            ("clone", ["git", "clone", "--quiet", "--branch", base_branch,
                       self.clone_url(repo), str(clone)]),
            ("checkout", [*git, "checkout", "--quiet", "-b", branch, base_sha]),
            ("apply", [*git, "-c", "user.name=Zebra", "-c", "user.email=zebra@zebra.gidley.co.uk",
                       "am", "--quiet", str(patch)]),
            ("push", [*git, "push", "--quiet", "origin", f"HEAD:refs/heads/{branch}"]),
        ]  # fmt: skip
        try:
            for label, step in steps:
                done = self.run(step, timeout=600)
                if done.returncode != 0:
                    return fail(f"{label} failed: {tail(done.stderr, 500)}")
            title = (request.get("mr_title") or job.get("title") or "Zebra build")[:200]
            description = request.get("mr_description") or ""
            mr = self.run(
                ["glab", "mr", "create", "--repo", repo, "--source-branch", branch,
                 "--target-branch", base_branch, "--draft", "--title", title,
                 "--description", description, "--yes"],
                timeout=120,
            )  # fmt: skip
            urls = re.findall(r"https://\S+/merge_requests/\d+", mr.stdout + mr.stderr)
            published = {"branch": branch, "mr_url": urls[-1] if urls else None, "at": _iso()}
            if mr.returncode != 0 or not urls:
                published["error"] = f"branch pushed, MR not created: {tail(mr.stderr, 500)}"
            write_json(job_dir / "published.json", published)
            self.audit(job_id, "published", branch=branch, mr_url=published["mr_url"])
        finally:
            shutil.rmtree(clone, ignore_errors=True)

    # ---- probe

    def probe(self) -> dict:
        """Run the real sandbox command with an escape probe instead of Claude Code.

        The probe (``deploy/builder/sandbox-probe.sh`` in the image) reports what the sandbox can
        see and do; this checks it against what the sandbox is allowed. A dummy token stands in
        for the real one.
        """
        job_id = uuid.uuid4().hex
        job_dir = self.config.spool / f"probe-{job_id[:12]}"
        workspace, out = job_dir / "workspace", job_dir / "sandbox"
        workspace.mkdir(parents=True)
        out.mkdir()
        name = f"zebra-probe-{job_id[:12]}"
        job = {"title": "probe", "budget": {"max_turns": 1}}
        cmd = self.sandbox_command(
            job_id, job, name, workspace, out, "0" * 40, entrypoint="/usr/local/bin/sandbox-probe"
        )
        cmd.remove("--detach")
        try:
            env = {**os.environ, "CLAUDE_CODE_OAUTH_TOKEN": PROBE_TOKEN}
            done = self.run(cmd, env=env, timeout=300)
            report = read_json(out / "probe.json")
            if report is None:
                return {"ok": False, "failures": [f"no probe report: {tail(done.stderr, 500)}"]}
            failures = check_probe(report)
            return {"ok": not failures, "failures": failures, "report": report}
        finally:
            self.run(["podman", "rm", "-f", name], timeout=60)
            shutil.rmtree(job_dir, ignore_errors=True)

    # ---- prune

    def prune(self) -> None:
        """Delete finished job directories older than ``prune_days``."""
        cutoff = _now() - self.config.prune_days * 86400
        for job_dir in self.job_dirs():
            status = read_json(job_dir / "status.json") or {}
            if status.get("state") in TERMINAL_STATES and job_dir.stat().st_mtime < cutoff:
                shutil.rmtree(job_dir, ignore_errors=True)


PROBE_TOKEN = "zebra-probe-token"
# Environment the sandbox may see: the image's own, podman's, and what sandbox_command passes.
PROBE_ALLOWED_ENV = {
    "PATH", "HOME", "HOSTNAME", "TERM", "container", "NODE_VERSION", "YARN_VERSION",
    "UV_PYTHON_INSTALL_DIR", "UV_TOOL_BIN_DIR", "PWD", "SHLVL", "_",
    "LC_CTYPE",  # set by Python's own locale coercion (PEP 538) in the probe
    "CLAUDE_CODE_OAUTH_TOKEN", "MAX_TURNS", "BASE_SHA", "BUILD_TITLE", "TEST_COMMAND",
}  # fmt: skip
# Host-filesystem mounts podman itself adds to every container.
PROBE_ALLOWED_MOUNTS = {
    "/workspace", "/out", "/etc/hosts", "/etc/resolv.conf", "/etc/hostname",
    "/run/.containerenv", "/etc/passwd", "/etc/group",
}  # fmt: skip


def check_probe(report: dict) -> list[str]:
    """Compare a sandbox probe report with what the sandbox is allowed; return the failures."""
    failures = []
    if report.get("uid") in (0, None):
        failures.append(f"runs as uid {report.get('uid')}, not an unprivileged user")
    if str(report.get("cap_eff", "")).strip("0"):
        failures.append(f"has effective capabilities {report.get('cap_eff')}")
    if str(report.get("no_new_privs")) != "1":
        failures.append("no_new_privs is not set")
    extra_env = sorted(set(report.get("env_names", [])) - PROBE_ALLOWED_ENV)
    if extra_env:
        failures.append(f"unexpected environment variables: {', '.join(extra_env)}")
    if report.get("token_seen") != PROBE_TOKEN:
        failures.append("the Claude token was not passed through")
    extra_mounts = sorted(set(report.get("host_mounts", [])) - PROBE_ALLOWED_MOUNTS)
    if extra_mounts:
        failures.append(f"unexpected host mounts: {', '.join(extra_mounts)}")
    for path in report.get("host_paths_visible", []):
        failures.append(f"host path visible: {path}")
    for path in report.get("writable_outside", []):
        failures.append(f"can write outside /workspace and /out: {path}")
    if report.get("podman_socket"):
        failures.append("a podman/docker socket is reachable")
    if not report.get("workspace_writable"):
        failures.append("/workspace is not writable")
    return failures


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--once", action="store_true", help="process the spool once and exit")
    parser.add_argument("--interval", type=float, default=5.0, help="seconds between passes")
    parser.add_argument(
        "--probe", action="store_true", help="run the sandbox escape probe, print the report"
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    config = Config.from_env(os.environ)
    config.spool.mkdir(parents=True, exist_ok=True)
    builder = Builder(config)
    if args.probe:
        outcome = builder.probe()
        print(json.dumps(outcome, indent=2))
        return 0 if outcome["ok"] else 1
    logger.info(
        "builder started: spool=%s repos=%s ceilings=%d turns/%d min token=%s",
        config.spool, ",".join(config.repos), config.max_turns, config.max_minutes,
        "set" if config.token else "MISSING",
    )  # fmt: skip

    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while True:
        builder.tick()
        if args.once or stopping:
            return 0
        deadline = _now() + args.interval
        while not stopping and _now() < deadline:
            time.sleep(0.5)


if __name__ == "__main__":
    raise SystemExit(main())
