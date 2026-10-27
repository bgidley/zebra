"""Tests for scripts/zebra_builder.py, the host builder for Claude Code builds (#98, #172).

A fake command runner stands in for git, podman and glab, so these run anywhere. The real
sandbox is checked on the host with ``zebra_builder.py --probe``.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "zebra_builder.py"
TOKEN = "sk-ant-oat-test-token-123"
BASE_SHA = "a" * 40


@pytest.fixture(scope="module")
def zb():
    spec = importlib.util.spec_from_file_location("zebra_builder", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["zebra_builder"] = module
    spec.loader.exec_module(module)
    return module


class FakeRunner:
    """Pretends to be git / podman / glab. Records every call."""

    def __init__(self):
        self.calls: list[tuple[list[str], dict]] = []
        self.container_state: dict[str, str] = {}  # name -> "running 0" / "exited 0"; absent = gone
        self.fail: set[str] = set()  # labels: "clone", "push", ...
        self.mr_url = "https://gitlab.com/gidley/zebra/-/merge_requests/42"
        self.heads: dict[str, str] = {}  # branch -> sha on the remote (git ls-remote)
        self.api: dict[str, object] = {}  # path fragment -> JSON answer (glab api)

    def __call__(self, args, *, cwd=None, env=None, timeout=None):
        args = list(args)
        self.calls.append((args, dict(env or {})))
        ok = subprocess.CompletedProcess(args, 0, "", "")
        if args[:2] == ["git", "ls-remote"]:
            branch = args[-1].removeprefix("refs/heads/")
            sha = self.heads.get(branch)
            return subprocess.CompletedProcess(args, 0, f"{sha}\t{args[-1]}\n" if sha else "", "")
        if args[:2] == ["glab", "api"]:
            for fragment, answer in self.api.items():
                if fragment in args[2]:
                    return subprocess.CompletedProcess(args, 0, json.dumps(answer), "")
            return subprocess.CompletedProcess(args, 1, "", "404 Not Found")
        if args[:2] == ["git", "clone"]:
            if "clone" in self.fail:
                return subprocess.CompletedProcess(args, 128, "", "fatal: no such repo")
            Path(args[-1]).mkdir(parents=True)
            return ok
        if args[:1] == ["git"] and "rev-parse" in args:
            return subprocess.CompletedProcess(args, 0, BASE_SHA + "\n", "")
        if args[:1] == ["git"] and "push" in args and "push" in self.fail:
            return subprocess.CompletedProcess(args, 1, "", "rejected")
        if "podman" in args and "run" in args:
            name = args[args.index("--name") + 1]
            self.container_state[name] = "running 0"
            return ok
        if args[:2] == ["podman", "inspect"]:
            state = self.container_state.get(args[-1])
            if state is None:
                return subprocess.CompletedProcess(args, 125, "", "no such container")
            return subprocess.CompletedProcess(args, 0, state + "\n", "")
        if args[:2] == ["podman", "rm"]:
            self.container_state.pop(args[-1], None)
            return ok
        if args[:3] == ["glab", "mr", "create"]:
            return subprocess.CompletedProcess(args, 0, f"Created {self.mr_url}\n", "")
        return ok

    def commands(self, first: str) -> list[list[str]]:
        return [a for a, _ in self.calls if a and (a[0] == first or first in a[:4])]

    def podman_runs(self) -> list[tuple[list[str], dict]]:
        return [(a, e) for a, e in self.calls if "podman" in a and "run" in a]


@pytest.fixture
def config(zb, tmp_path):
    return zb.Config(
        spool=tmp_path / "builds",
        repos=("gidley/zebra",),
        max_turns=200,
        max_minutes=90,
        token=TOKEN,
    )


@pytest.fixture
def runner():
    return FakeRunner()


@pytest.fixture
def builder(zb, config, runner):
    config.spool.mkdir()
    return zb.Builder(config, runner)


def make_job(config, job_id: str | None = None, **overrides) -> Path:
    job_id = job_id or os.urandom(16).hex()
    job = {
        "kind": "build",
        "repo": "gidley/zebra",
        "base_branch": "master",
        "title": "Add a greeting",
        "prompt": "Add a hello() function with a test.",
        "test_command": "uv run pytest -q",
        "budget": {"max_turns": 50, "minutes": 30},
        "process_id": "proc-1",
    }
    job.update(overrides)
    job_dir = config.spool / job_id
    job_dir.mkdir()
    (job_dir / "job.json").write_text(json.dumps(job))
    return job_dir


def read(job_dir: Path, name: str) -> dict:
    return json.loads((job_dir / name).read_text())


def audit_events(config) -> list[dict]:
    path = config.spool / "audit.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def finish_sandbox(job_dir: Path, runner: FakeRunner, *, claude=None, patch="PATCH", **files):
    """Simulate a sandbox that ran to the end and left its outputs."""
    out = job_dir / "sandbox"
    claude = claude if claude is not None else {
        "type": "result", "subtype": "success", "is_error": False, "num_turns": 12,
        "total_cost_usd": 1.25, "result": "Added hello() and a test.",
    }  # fmt: skip
    (out / "claude.json").write_text(json.dumps(claude) if isinstance(claude, dict) else claude)
    if patch is not None:
        (out / "changes.patch").write_text(patch)
    (out / "diffstat.txt").write_text(files.pop("diffstat", " hello.py | 3 +++\n 1 file changed"))
    (out / "test.rc").write_text(files.pop("test_rc", "0"))
    (out / "test.log").write_text(files.pop("test_log", "1 passed"))
    for name, text in files.items():
        (out / name).write_text(text)
    for name in list(runner.container_state):
        runner.container_state[name] = "exited 0"


# --------------------------------------------------------------------------- validation


class TestValidateJob:
    def test_valid_job(self, zb, config):
        job = {
            "kind": "build", "repo": "gidley/zebra", "base_branch": "master", "title": "t",
            "prompt": "p", "budget": {"max_turns": 10, "minutes": 5},
        }  # fmt: skip
        assert zb.validate_job(job, config) == (None, [])

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("kind", "shell"),
            ("repo", "../etc"),
            ("base_branch", "-oProxyCommand=x"),
            ("base_branch", "a..b"),
            ("title", ""),
            ("prompt", ""),
            ("budget", None),
        ],
    )
    def test_malformed_fields_are_errors(self, zb, config, field, value):
        job = {
            "kind": "build", "repo": "gidley/zebra", "base_branch": "master", "title": "t",
            "prompt": "p", "budget": {"max_turns": 10, "minutes": 5},
        }  # fmt: skip
        job[field] = value
        error, _ = zb.validate_job(job, config)
        assert error

    @pytest.mark.parametrize("value", [0, -1, True, "10", 1.5])
    def test_budget_must_be_positive_int(self, zb, config, value):
        job = {
            "kind": "build", "repo": "gidley/zebra", "base_branch": "master", "title": "t",
            "prompt": "p", "budget": {"max_turns": value, "minutes": 5},
        }  # fmt: skip
        error, _ = zb.validate_job(job, config)
        assert error == "budget.max_turns must be a positive integer"

    def test_over_ceilings_and_unlisted_repo_are_violations(self, zb, config):
        job = {
            "kind": "build", "repo": "someone/else", "base_branch": "main", "title": "t",
            "prompt": "p", "budget": {"max_turns": 500, "minutes": 600},
        }  # fmt: skip
        error, violations = zb.validate_job(job, config)
        assert error is None
        assert {v["limit"] for v in violations} == {"repo", "max_turns", "minutes"}
        assert {"limit": "max_turns", "requested": 500, "allowed": 200} in violations


# --------------------------------------------------------------------------- start


class TestStart:
    def test_rejected_job_starts_nothing_and_is_audited(self, builder, config, runner):
        job_dir = make_job(config, repo="evil/repo", budget={"max_turns": 999, "minutes": 5})
        builder.tick()

        result = read(job_dir, "result.json")
        assert result["state"] == "rejected"
        assert {v["limit"] for v in result["violations"]} == {"repo", "max_turns"}
        assert runner.calls == []  # no clone, no container
        events = audit_events(config)
        assert events[-1]["event"] == "rejected"
        assert events[-1]["job_id"] == job_dir.name

    def test_missing_token_fails_without_starting(self, zb, config, runner):
        config.spool.mkdir()
        builder = zb.Builder(zb.Config(spool=config.spool, token=""), runner)
        job_dir = make_job(config)
        builder.tick()
        assert read(job_dir, "result.json")["state"] == "failed"
        assert "CLAUDE_CODE_OAUTH_TOKEN" in read(job_dir, "result.json")["error"]
        assert runner.podman_runs() == []

    def test_clone_failure_fails_the_job(self, builder, config, runner):
        runner.fail.add("clone")
        job_dir = make_job(config)
        builder.tick()
        assert read(job_dir, "result.json")["state"] == "failed"
        assert runner.podman_runs() == []

    def test_sandbox_command_is_constrained(self, builder, config, runner):
        job_dir = make_job(config)
        builder.tick()

        [(cmd, env)] = runner.podman_runs()
        assert cmd[:3] == ["nice", "-n", "10"]
        assert "--userns=keep-id" in cmd
        assert f"--user={os.getuid()}:{os.getgid()}" in cmd
        assert "--memory=3g" in cmd and "--memory-swap=3g" in cmd
        assert "--pids-limit=512" in cmd
        assert "--cap-drop=all" in cmd
        assert "--security-opt=no-new-privileges" in cmd
        mounts = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-v"]
        assert mounts == [
            f"{job_dir / 'workspace'}:/workspace:Z",
            f"{job_dir / 'sandbox'}:/out:Z",
        ]
        env_args = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-e"]
        assert "CLAUDE_CODE_OAUTH_TOKEN" in env_args  # by name only
        assert {e.split("=", 1)[0] for e in env_args} == {
            "CLAUDE_CODE_OAUTH_TOKEN", "HOME", "MAX_TURNS", "BASE_SHA", "BUILD_TITLE",
            "TEST_COMMAND",
        }  # fmt: skip
        assert "MAX_TURNS=50" in env_args
        assert not any(TOKEN in a for a in cmd)  # never in argv
        assert env["CLAUDE_CODE_OAUTH_TOKEN"] == TOKEN
        assert "--privileged" not in cmd and "--network=host" not in cmd

        status = read(job_dir, "status.json")
        assert status["state"] == "running"
        assert status["base_sha"] == BASE_SHA
        prompt = (job_dir / "sandbox" / "prompt.md").read_text()
        assert "Add a hello() function" in prompt and "no credentials for pushing" in prompt

    def test_cpus_only_when_configured(self, zb, config, runner):
        config.spool.mkdir()
        builder = zb.Builder(zb.Config(spool=config.spool, token=TOKEN, cpus="1.5"), runner)
        make_job(config)
        builder.tick()
        [(cmd, _)] = runner.podman_runs()
        assert "--cpus=1.5" in cmd

    def test_one_build_at_a_time(self, builder, config, runner):
        first = make_job(config)
        time.sleep(0.01)
        second = make_job(config)
        builder.tick()
        builder.tick()
        assert len(runner.podman_runs()) == 1
        assert read(first, "status.json")["state"] == "running"
        assert read(second, "status.json")["state"] == "queued"

    def test_older_queued_job_waits_for_the_running_one(self, builder, config, runner):
        older = make_job(config)
        week_ago = time.time() - 3600
        os.utime(older / "job.json", (week_ago, week_ago))
        (older / "status.json").write_text(json.dumps({"state": "queued"}))
        newer = make_job(config)
        # Pretend `newer` is already running (started by an earlier pass).
        builder.start(newer)
        runner.calls.clear()
        os.utime(newer, None)  # a status write bumps the directory mtime
        builder.tick()
        assert runner.podman_runs() == []
        assert read(older, "status.json")["state"] == "queued"

    def test_ignores_non_job_directories(self, builder, config, runner):
        (config.spool / "not-a-job").mkdir()
        (config.spool / "probe-abc").mkdir()
        builder.tick()
        assert runner.calls == []


# --------------------------------------------------------------------------- collect


class TestCollect:
    def test_successful_build(self, builder, config, runner):
        job_dir = make_job(config)
        builder.tick()
        finish_sandbox(job_dir, runner, patch="From abc\n+def hello(): ...\n")
        builder.tick()

        result = read(job_dir, "result.json")
        assert result["state"] == "done"
        assert result["turns"] == 12
        assert result["notional_cost_usd"] == 1.25
        assert result["summary"] == "Added hello() and a test."
        assert result["test"] == {"command": "uv run pytest -q", "rc": 0, "log_tail": "1 passed"}
        assert "def hello" in result["patch_excerpt"]
        assert result["patch_sha256"] == builder_sha("From abc\n+def hello(): ...\n")
        assert (job_dir / "changes.patch").read_text().startswith("From abc")
        assert not (job_dir / "workspace").exists()  # hostile workspace gone
        assert runner.container_state == {}  # container removed

    def test_failing_tests_are_reported_not_hidden(self, builder, config, runner):
        job_dir = make_job(config)
        builder.tick()
        finish_sandbox(job_dir, runner, test_rc="1", test_log="1 failed")
        builder.tick()
        result = read(job_dir, "result.json")
        assert result["state"] == "done"
        assert result["test"]["rc"] == 1

    def test_sensitive_paths_are_flagged(self, builder, config, runner):
        job_dir = make_job(config)
        builder.tick()
        finish_sandbox(
            job_dir, runner,
            diffstat=" .gitlab-ci.yml | 2 +-\n scripts/x.sh | 1 +\n app.py | 4 ++--\n",
        )  # fmt: skip
        builder.tick()
        assert read(job_dir, "result.json")["sensitive_files"] == [".gitlab-ci.yml", "scripts/x.sh"]

    def test_max_turns_is_over_budget_and_audited(self, builder, config, runner):
        job_dir = make_job(config)
        builder.tick()
        finish_sandbox(
            job_dir, runner,
            claude={"subtype": "error_max_turns", "is_error": True, "num_turns": 50},
        )  # fmt: skip
        builder.tick()
        result = read(job_dir, "result.json")
        assert result["state"] == "over_budget"
        assert result["violations"] == [{"limit": "max_turns", "used": 50, "allowed": 50}]
        assert audit_events(config)[-1]["event"] == "over_budget"
        assert audit_events(config)[-1]["limit"] == "max_turns"

    def test_minutes_exceeded_kills_the_sandbox(self, builder, config, runner):
        job_dir = make_job(config)
        builder.tick()
        status = read(job_dir, "status.json")
        status["started_at"] = time.time() - 31 * 60
        (job_dir / "status.json").write_text(json.dumps(status))
        builder.tick()

        result = read(job_dir, "result.json")
        assert result["state"] == "over_budget"
        assert result["violations"][0]["limit"] == "minutes"
        assert result["violations"][0]["allowed"] == 30
        assert any(a[:3] == ["podman", "rm", "-f"] for a in runner.commands("podman"))
        assert runner.container_state == {}
        assert audit_events(config)[-1]["limit"] == "minutes"

    def test_malformed_claude_result_fails(self, builder, config, runner):
        job_dir = make_job(config)
        builder.tick()
        finish_sandbox(job_dir, runner, claude="not json{")
        builder.tick()
        result = read(job_dir, "result.json")
        assert result["state"] == "failed"
        assert "did not finish cleanly" in result["error"]

    def test_no_changes_fails(self, builder, config, runner):
        job_dir = make_job(config)
        builder.tick()
        finish_sandbox(job_dir, runner, patch="")
        builder.tick()
        assert read(job_dir, "result.json")["error"] == "Claude Code made no changes"

    def test_symlinked_output_is_never_followed(self, builder, config, runner, tmp_path):
        secret = tmp_path / "prod.env"
        secret.write_text("ORACLE_PASSWORD=hunter2")
        job_dir = make_job(config)
        builder.tick()
        finish_sandbox(job_dir, runner, patch=None)
        (job_dir / "sandbox" / "changes.patch").symlink_to(secret)
        (job_dir / "sandbox" / "test.log").unlink()
        (job_dir / "sandbox" / "test.log").symlink_to(secret)
        builder.tick()

        text = (job_dir / "result.json").read_text()
        assert "hunter2" not in text
        assert read(job_dir, "result.json")["error"] == "Claude Code made no changes"
        assert secret.read_text() == "ORACLE_PASSWORD=hunter2"  # untouched by cleanup

    def test_token_is_redacted_from_text_that_leaves_the_host(self, builder, config, runner):
        job_dir = make_job(config)
        builder.tick()
        finish_sandbox(
            job_dir, runner, test_log=f"env: CLAUDE_CODE_OAUTH_TOKEN={TOKEN}",
            claude={"subtype": "success", "num_turns": 3, "result": f"token is {TOKEN}"},
        )  # fmt: skip
        builder.tick()
        text = (job_dir / "result.json").read_text()
        assert TOKEN not in text
        assert "[REDACTED]" in text

    def test_patch_containing_the_token_is_refused(self, builder, config, runner):
        job_dir = make_job(config)
        builder.tick()
        finish_sandbox(job_dir, runner, patch=f"+TOKEN = '{TOKEN}'\n")
        builder.tick()
        result = read(job_dir, "result.json")
        assert result["state"] == "failed"
        assert TOKEN not in (job_dir / "result.json").read_text()
        assert not (job_dir / "changes.patch").exists()


class TestReadOutput:
    def test_refuses_oversized_files(self, zb, tmp_path):
        big = tmp_path / "big"
        big.write_text("x" * 101)
        assert zb.read_output(big, 100) is None
        assert zb.read_output(big, 101) == "x" * 101

    def test_refuses_directories_and_missing(self, zb, tmp_path):
        assert zb.read_output(tmp_path, 100) is None
        assert zb.read_output(tmp_path / "nope", 100) is None


# --------------------------------------------------------------------------- restart / cancel


class TestRestartAndCancel:
    def test_restarted_builder_reattaches_to_running_sandbox(self, zb, builder, config, runner):
        job_dir = make_job(config)
        builder.tick()
        fresh = zb.Builder(config, runner)  # a new process: no in-memory state
        fresh.tick()
        assert read(job_dir, "status.json")["state"] == "running"
        assert not (job_dir / "result.json").exists()
        assert len(runner.podman_runs()) == 1  # not started again

    def test_job_whose_sandbox_is_gone_fails(self, builder, config, runner):
        job_dir = make_job(config)
        builder.tick()
        runner.container_state.clear()
        builder.tick()
        result = read(job_dir, "result.json")
        assert result["state"] == "failed"
        assert "gone" in result["error"]

    def test_cancel_while_running_kills_the_sandbox(self, builder, config, runner):
        job_dir = make_job(config)
        builder.tick()
        (job_dir / "cancel").touch()
        builder.tick()
        assert read(job_dir, "result.json")["state"] == "cancelled"
        assert runner.container_state == {}
        assert not (job_dir / "workspace").exists()
        assert audit_events(config)[-1]["event"] == "cancelled"

    def test_cancel_before_start(self, builder, config, runner):
        job_dir = make_job(config)
        (job_dir / "cancel").touch()
        builder.tick()
        assert read(job_dir, "result.json")["state"] == "cancelled"
        assert runner.calls == []

    def test_next_job_starts_after_the_first_finishes(self, builder, config, runner):
        first = make_job(config)
        time.sleep(0.01)
        second = make_job(config)
        builder.tick()
        finish_sandbox(first, runner)
        builder.tick()  # collects first
        builder.tick()  # starts second
        assert read(second, "status.json")["state"] == "running"


# --------------------------------------------------------------------------- publish


def builder_sha(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode()).hexdigest()


def built_job(builder, config, runner, patch="From abc\n+x\n") -> Path:
    job_dir = make_job(config)
    builder.tick()
    finish_sandbox(job_dir, runner, patch=patch)
    builder.tick()
    assert read(job_dir, "result.json")["state"] == "done"
    runner.calls.clear()
    return job_dir


class TestPublish:
    def test_publish_pushes_build_branch_from_fresh_clone(self, builder, config, runner):
        job_dir = built_job(builder, config, runner)
        sha = read(job_dir, "result.json")["patch_sha256"]
        (job_dir / "publish.json").write_text(
            json.dumps({"mr_title": "Add hello", "mr_description": "d", "patch_sha256": sha})
        )
        builder.tick()

        published = read(job_dir, "published.json")
        branch = f"zebra-build/{job_dir.name[:12]}"
        assert published["branch"] == branch
        assert published["mr_url"] == runner.mr_url
        git_calls = [a for a, _ in runner.calls if a[0] == "git"]
        clone_dir = str(job_dir / "publish")
        assert git_calls[0][:2] == ["git", "clone"] and git_calls[0][-1] == clone_dir
        for call in git_calls[1:]:
            assert call[:3] == ["git", "-C", clone_dir]  # never the sandbox workspace
            assert "core.hooksPath=/dev/null" in call
        [push] = [a for a in git_calls if "push" in a]
        assert push[-1] == f"HEAD:refs/heads/{branch}"
        [mr] = [a for a, _ in runner.calls if a[:3] == ["glab", "mr", "create"]]
        assert "--draft" in mr
        assert mr[mr.index("--target-branch") + 1] == "master"
        assert not (job_dir / "publish").exists()
        assert audit_events(config)[-1]["event"] == "published"

    def test_publish_happens_once(self, builder, config, runner):
        job_dir = built_job(builder, config, runner)
        sha = read(job_dir, "result.json")["patch_sha256"]
        (job_dir / "publish.json").write_text(json.dumps({"patch_sha256": sha}))
        builder.tick()
        builder.tick()
        pushes = [a for a, _ in runner.calls if a[0] == "git" and "push" in a]
        assert len(pushes) == 1

    def test_stale_approval_is_refused(self, builder, config, runner):
        job_dir = built_job(builder, config, runner)
        (job_dir / "publish.json").write_text(json.dumps({"patch_sha256": "0" * 64}))
        builder.tick()
        assert "does not match" in read(job_dir, "published.json")["error"]
        assert not any("push" in a for a, _ in runner.calls)

    def test_repo_removed_from_allowlist_is_refused(self, zb, builder, config, runner):
        job_dir = built_job(builder, config, runner)
        sha = read(job_dir, "result.json")["patch_sha256"]
        (job_dir / "publish.json").write_text(json.dumps({"patch_sha256": sha}))
        locked = zb.Builder(
            zb.Config(spool=config.spool, repos=("other/repo",), token=TOKEN), runner
        )
        locked.tick()
        assert "not publishable" in read(job_dir, "published.json")["error"]
        assert not any("push" in a for a, _ in runner.calls)

    def test_push_failure_is_reported(self, builder, config, runner):
        job_dir = built_job(builder, config, runner)
        sha = read(job_dir, "result.json")["patch_sha256"]
        (job_dir / "publish.json").write_text(json.dumps({"patch_sha256": sha}))
        runner.fail.add("push")
        builder.tick()
        assert read(job_dir, "published.json")["error"].startswith("push failed")
        assert not any(a[:3] == ["glab", "mr", "create"] for a, _ in runner.calls)

    def test_no_publish_without_request(self, builder, config, runner):
        built_job(builder, config, runner)
        builder.tick()
        assert runner.calls == []


# --------------------------------------------------------------------------- prune, probe


def test_prune_removes_old_finished_jobs(zb, builder, config, runner):
    old = built_job(builder, config, runner)
    week_ago = time.time() - 8 * 86400
    os.utime(old, (week_ago, week_ago))
    running = make_job(config)
    builder.tick()  # starts `running`, prunes `old`
    assert not old.exists()
    assert running.exists()


class TestCheckProbe:
    def good(self, zb):
        return {
            "uid": 1000, "cap_eff": "0000000000000000", "no_new_privs": "1",
            "env_names": ["PATH", "HOME", "CLAUDE_CODE_OAUTH_TOKEN"],
            "token_seen": zb.PROBE_TOKEN, "host_mounts": ["/out", "/workspace"],
            "host_paths_visible": [], "writable_outside": [], "podman_socket": False,
            "workspace_writable": True,
        }  # fmt: skip

    def test_clean_report_passes(self, zb):
        assert zb.check_probe(self.good(zb)) == []

    @pytest.mark.parametrize(
        ("key", "value", "expected"),
        [
            ("uid", 0, "uid 0"),
            ("cap_eff", "00000000a80425fb", "capabilities"),
            ("no_new_privs", "0", "no_new_privs"),
            ("env_names", ["PATH", "ORACLE_PASSWORD"], "ORACLE_PASSWORD"),
            ("host_mounts", ["/workspace", "/home/opc"], "/home/opc"),
            ("host_paths_visible", ["/home/opc/.config/zebra"], "host path visible"),
            ("writable_outside", ["/usr"], "write outside"),
            ("podman_socket", True, "socket"),
            ("token_seen", None, "token was not passed"),
        ],
    )
    def test_each_escape_is_caught(self, zb, key, value, expected):
        report = self.good(zb)
        report[key] = value
        failures = zb.check_probe(report)
        assert len(failures) == 1 and expected in failures[0]


def test_config_from_env(zb):
    config = zb.Config.from_env(
        {
            "HOME": "/home/opc",
            "ZEBRA_BUILDER_REPOS": "gidley/zebra, gidley/other ",
            "ZEBRA_BUILDER_MAX_TURNS": "80",
            "CLAUDE_CODE_OAUTH_TOKEN": "t",
        }
    )
    assert config.spool == Path("/home/opc/.local/share/zebra/builds")
    assert config.repos == ("gidley/zebra", "gidley/other")
    assert config.max_turns == 80
    assert config.max_minutes == 90
    assert config.token == "t"


# --------------------------------------------------------------------------- delivery stages

GITLAB_DEV = "glpat-dev-token-123456"
GITLAB_MERGE = "glpat-merge-token-654321"
GITHUB = "github_pat_test_token_abcdef"
HEAD_SHA = "b" * 40
MERGE_SHA = "c" * 40


@pytest.fixture
def stage_config(zb, tmp_path):
    return zb.Config(
        spool=tmp_path / "builds",
        token=TOKEN,
        gitlab_token=GITLAB_DEV,
        gitlab_merge_token=GITLAB_MERGE,
        github_token=GITHUB,
    )


@pytest.fixture
def stage_builder(zb, stage_config, runner):
    stage_config.spool.mkdir()
    return zb.Builder(stage_config, runner)


def make_stage_job(config, stage: str, **overrides) -> Path:
    fields = {"stage": stage, "branch": "f251/builder-stages", "issue": 251, "test_command": ""}
    fields.update(overrides)
    return make_job(config, **fields)


def stage_job_dict(**overrides) -> dict:
    job = {
        "kind": "build", "repo": "gidley/zebra", "base_branch": "master", "title": "t",
        "prompt": "p", "budget": {"max_turns": 5, "minutes": 5}, "stage": "ship",
        "branch": "f1/x", "issue": 1,
    }  # fmt: skip
    job.update(overrides)
    return job


def env_args(cmd: list[str]) -> list[str]:
    return [cmd[i + 1] for i, a in enumerate(cmd) if a == "-e"]


def finish_stage(job_dir: Path, runner: FakeRunner, report: dict | str | None = None) -> None:
    """Simulate a stage sandbox that ran to the end and wrote its report."""
    finish_sandbox(job_dir, runner, patch=None)
    if report is not None:
        text = report if isinstance(report, str) else json.dumps(report)
        (job_dir / "sandbox" / "report.json").write_text(text)


def shipped_job(builder, config, runner) -> Path:
    """A finished ship job whose result recorded HEAD_SHA."""
    job_dir = make_stage_job(config, "ship")
    builder.tick()
    runner.heads["f251/builder-stages"] = HEAD_SHA
    runner.api["repository/compare"] = {"diffs": [{"new_path": "x.py", "diff": "+x"}]}
    finish_stage(job_dir, runner, {"pr_url": "https://github.com/bgidley/zebra/pull/9"})
    builder.tick()
    assert read(job_dir, "result.json")["head_sha"] == HEAD_SHA
    runner.calls.clear()
    return job_dir


class TestStageValidation:
    @pytest.mark.parametrize("stage", ["propose", "ship", "review"])
    def test_valid_stage_jobs(self, zb, stage_config, stage):
        assert zb.validate_job(stage_job_dict(stage=stage), stage_config) == (None, [])

    @pytest.mark.parametrize(
        ("overrides", "expected"),
        [
            ({"stage": "deploy"}, "stage must be"),
            ({"issue": 0}, "issue"),
            ({"issue": "251"}, "issue"),
            ({"issue": True}, "issue"),
            ({"branch": "master"}, "branch"),
            ({"branch": "../x"}, "branch"),
            ({"branch": None}, "branch"),
        ],
    )
    def test_bad_stage_fields_are_errors(self, zb, stage_config, overrides, expected):
        error, _ = zb.validate_job(stage_job_dict(**overrides), stage_config)
        assert error and expected in error

    @pytest.mark.parametrize(
        "approval",
        [None, {"ship_job_id": "x", "head_sha": HEAD_SHA}, {"ship_job_id": "a" * 32}],
    )
    def test_merge_needs_a_well_formed_approval(self, zb, stage_config, approval):
        error, _ = zb.validate_job(stage_job_dict(stage="merge", approval=approval), stage_config)
        assert "approval" in error

    def test_stages_only_run_on_the_self_repo(self, zb, stage_config):
        config = zb.Config(spool=stage_config.spool, repos=("gidley/zebra", "gidley/other"))
        _, violations = zb.validate_job(stage_job_dict(repo="gidley/other"), config)
        assert [v["limit"] for v in violations] == ["stage_repo"]

    def test_jobs_without_a_stage_are_patch_builds(self, zb):
        assert zb.job_stage({"kind": "build"}) == "patch"


class TestStageStart:
    @pytest.mark.parametrize(
        ("stage", "expected"),
        [
            ("propose", {"GITLAB_TOKEN": GITLAB_DEV}),
            ("ship", {"GITLAB_TOKEN": GITLAB_DEV, "GH_TOKEN": GITHUB}),
            ("review", {"GITLAB_TOKEN": GITLAB_DEV}),
        ],
    )
    def test_each_stage_gets_only_its_credentials_by_name(
        self, stage_builder, stage_config, runner, stage, expected
    ):
        job_dir = make_stage_job(stage_config, stage)
        stage_builder.tick()

        [(cmd, env)] = runner.podman_runs()
        assert cmd[cmd.index("--name") + 1] == f"zebra-build-{job_dir.name[:12]}"
        names = {e.split("=", 1)[0] for e in env_args(cmd)}
        assert names & {"GITLAB_TOKEN", "GH_TOKEN"} == set(expected)
        assert {"STAGE", "BRANCH", "ISSUE", "GITHUB_REPO", "GITLAB_HOST"} <= names
        for name, value in expected.items():
            assert name in env_args(cmd)  # by name only
            assert env[name] == value
        for secret in (GITLAB_DEV, GITLAB_MERGE, GITHUB):
            assert not any(secret in a for a in cmd)  # never in argv
        assert GITLAB_MERGE not in env.values()

    def test_missing_stage_credential_fails_without_cloning(self, zb, config, runner):
        config.spool.mkdir()
        builder = zb.Builder(zb.Config(spool=config.spool, token=TOKEN, gitlab_token="x"), runner)
        job_dir = make_stage_job(config, "ship")
        builder.tick()
        result = read(job_dir, "result.json")
        assert result["state"] == "failed"
        assert "ZEBRA_BUILDER_GITHUB_TOKEN" in result["error"]
        assert runner.commands("git") == []

    def test_propose_creates_the_branch_before_the_sandbox_runs(
        self, stage_builder, stage_config, runner
    ):
        job_dir = make_stage_job(stage_config, "propose")
        stage_builder.tick()
        calls = [a for a, _ in runner.calls]
        [clone] = [a for a in calls if a[:2] == ["git", "clone"]]
        assert clone[clone.index("--branch") + 1] == "master"
        assert "--single-branch" not in clone
        [checkout] = [a for a in calls if "checkout" in a]
        assert checkout[-1] == "f251/builder-stages"
        assert calls.index(checkout) < calls.index(runner.podman_runs()[0][0])
        prompt = (job_dir / "sandbox" / "prompt.md").read_text()
        assert "stage `propose`" in prompt and "issue #251" in prompt
        assert "glab issue view 251" in prompt and "no credentials" not in prompt

    def test_ship_resumes_an_existing_branch(self, stage_builder, stage_config, runner):
        runner.heads["f251/builder-stages"] = HEAD_SHA
        make_stage_job(stage_config, "ship")
        stage_builder.tick()
        [clone] = [a for a, _ in runner.calls if a[:2] == ["git", "clone"]]
        assert clone[clone.index("--branch") + 1] == "f251/builder-stages"
        assert not any("checkout" in a for a, _ in runner.calls)


class TestMergeApproval:
    def merge_job(self, config, ship_dir, head=HEAD_SHA, **overrides):
        return make_stage_job(
            config,
            "merge",
            approval={"ship_job_id": ship_dir.name, "head_sha": head},
            **overrides,
        )

    def test_approved_head_starts_the_merge_with_the_merge_token(
        self, stage_builder, stage_config, runner
    ):
        ship_dir = shipped_job(stage_builder, stage_config, runner)
        job_dir = self.merge_job(stage_config, ship_dir)
        stage_builder.tick()
        [(_, env)] = runner.podman_runs()
        assert env["GITLAB_TOKEN"] == GITLAB_MERGE and env["GH_TOKEN"] == GITHUB
        prompt = (job_dir / "sandbox" / "prompt.md").read_text()
        assert f"git merge --no-ff {HEAD_SHA}" in prompt
        approved = audit_events(stage_config)[-1]  # provenance: what was approved, for whom
        assert approved["event"] == "merge_approved"
        assert approved["ship_job_id"] == ship_dir.name and approved["head_sha"] == HEAD_SHA
        assert (approved["issue"], approved["process_id"]) == (251, "proc-1")

    @pytest.mark.parametrize("change", ["head", "moved", "other_branch"])
    def test_mismatched_approval_is_rejected_without_cloning(
        self, stage_builder, stage_config, runner, change
    ):
        ship_dir = shipped_job(stage_builder, stage_config, runner)
        if change == "head":
            job_dir = self.merge_job(stage_config, ship_dir, head="d" * 40)
        elif change == "moved":
            runner.heads["f251/builder-stages"] = "e" * 40  # pushed after the approval
            job_dir = self.merge_job(stage_config, ship_dir)
        else:
            job_dir = self.merge_job(stage_config, ship_dir, branch="f9/other")
        stage_builder.tick()
        assert read(job_dir, "result.json")["state"] == "rejected"
        assert runner.podman_runs() == []
        assert not any(a[:2] == ["git", "clone"] for a, _ in runner.calls)
        assert audit_events(stage_config)[-1]["event"] == "rejected"

    def test_a_ship_that_failed_cannot_be_merged(self, stage_builder, stage_config, runner):
        ship_dir = make_stage_job(stage_config, "ship")
        stage_builder.tick()
        finish_stage(ship_dir, runner)  # pushed nothing
        stage_builder.tick()
        assert read(ship_dir, "result.json")["state"] == "failed"
        job_dir = self.merge_job(stage_config, ship_dir)
        stage_builder.tick()
        assert read(job_dir, "result.json")["state"] == "rejected"


class TestStageCollect:
    def test_ship_records_facts_from_the_remote(self, stage_builder, stage_config, runner):
        job_dir = make_stage_job(stage_config, "ship")
        stage_builder.tick()
        runner.heads["f251/builder-stages"] = HEAD_SHA
        runner.api["repository/compare"] = {
            "diffs": [{"new_path": "scripts/x.sh", "diff": "+a"}, {"new_path": "a.py"}]
        }
        runner.api["pipelines?sha="] = [{"id": 7, "status": "success", "web_url": "u", "x": 1}]
        finish_stage(job_dir, runner, {"pr_url": "https://github.com/bgidley/zebra/pull/9"})
        stage_builder.tick()

        result = read(job_dir, "result.json")
        assert result["state"] == "done" and result["stage"] == "ship"
        assert result["head_sha"] == HEAD_SHA
        assert result["changed_files"] == ["a.py", "scripts/x.sh"]
        assert result["sensitive_files"] == ["scripts/x.sh"]
        assert result["pipeline"] == {"id": 7, "status": "success", "web_url": "u"}
        assert result["report"]["pr_url"].endswith("/pull/9")
        assert "patch_sha256" not in result
        assert not (job_dir / "workspace").exists()

    def test_a_stage_that_pushed_nothing_fails(self, stage_builder, stage_config, runner):
        job_dir = make_stage_job(stage_config, "propose")
        stage_builder.tick()
        finish_stage(job_dir, runner, {"change": "x"})
        stage_builder.tick()
        result = read(job_dir, "result.json")
        assert result["state"] == "failed" and "did not push" in result["error"]

    def test_a_pushed_credential_fails_the_stage(self, stage_builder, stage_config, runner):
        job_dir = make_stage_job(stage_config, "ship")
        stage_builder.tick()
        runner.heads["f251/builder-stages"] = HEAD_SHA
        runner.api["repository/compare"] = {"diffs": [{"new_path": "a", "diff": f"+{GITHUB}"}]}
        finish_stage(job_dir, runner, {})
        stage_builder.tick()
        result = read(job_dir, "result.json")
        assert result["state"] == "failed" and "credential" in result["error"]
        assert audit_events(stage_config)[-1]["event"] == "secret_pushed"

    def test_credentials_are_redacted_from_the_report_and_summary(
        self, stage_builder, stage_config, runner
    ):
        job_dir = make_stage_job(stage_config, "review")
        stage_builder.tick()
        claude = {"subtype": "success", "is_error": False, "num_turns": 3,
                  "result": f"used {GITLAB_DEV}"}  # fmt: skip
        finish_sandbox(job_dir, runner, claude=claude, patch=None)
        (job_dir / "sandbox" / "report.json").write_text(
            json.dumps({"verdicts": [{"id": "O1", "verdict": "met", "evidence": GITHUB}]})
        )
        stage_builder.tick()
        text = (job_dir / "result.json").read_text()
        assert GITLAB_DEV not in text and GITHUB not in text
        assert read(job_dir, "result.json")["state"] == "done"

    def test_review_without_verdicts_fails(self, stage_builder, stage_config, runner):
        job_dir = make_stage_job(stage_config, "review")
        stage_builder.tick()
        finish_stage(job_dir, runner, "not json")
        stage_builder.tick()
        assert "verdicts" in read(job_dir, "result.json")["error"]

    def test_claude_failure_still_records_remote_facts(self, stage_builder, stage_config, runner):
        job_dir = make_stage_job(stage_config, "ship")
        stage_builder.tick()
        runner.heads["f251/builder-stages"] = HEAD_SHA
        finish_sandbox(
            job_dir, runner, claude={"subtype": "error_max_turns", "num_turns": 9}, patch=None
        )
        stage_builder.tick()
        result = read(job_dir, "result.json")
        assert result["state"] == "over_budget" and result["head_sha"] == HEAD_SHA


class TestMergeCollect:
    def start_merge(self, builder, config, runner) -> Path:
        ship_dir = shipped_job(builder, config, runner)
        runner.heads["master"] = BASE_SHA
        job_dir = make_stage_job(
            config, "merge", approval={"ship_job_id": ship_dir.name, "head_sha": HEAD_SHA}
        )
        builder.tick()
        assert read(job_dir, "status.json")["base_head"] == BASE_SHA
        return job_dir

    def merged(self, builder, config, runner, parents) -> Path:
        job_dir = self.start_merge(builder, config, runner)
        runner.heads["master"] = MERGE_SHA
        runner.api["repository/commits/"] = {"parent_ids": parents}
        runner.api["pipelines?sha="] = [{"id": 8, "status": "running", "web_url": "m"}]
        finish_stage(job_dir, runner, {"merge_sha": MERGE_SHA})
        builder.tick()
        return job_dir

    def test_merge_of_the_approved_commit(self, stage_builder, stage_config, runner):
        job_dir = self.merged(stage_builder, stage_config, runner, [BASE_SHA, HEAD_SHA])
        result = read(job_dir, "result.json")
        assert result["state"] == "done"
        assert result["merge_sha"] == MERGE_SHA
        assert result["pipeline"]["status"] == "running"

    def test_merge_of_something_else_fails_loudly(self, stage_builder, stage_config, runner):
        job_dir = self.merged(stage_builder, stage_config, runner, [BASE_SHA, "f" * 40])
        result = read(job_dir, "result.json")
        assert result["state"] == "failed" and "approved commit" in result["error"]
        assert audit_events(stage_config)[-1]["event"] == "merge_mismatch"

    def test_master_that_did_not_move_fails(self, stage_builder, stage_config, runner):
        job_dir = self.start_merge(stage_builder, stage_config, runner)
        finish_stage(job_dir, runner, {})
        stage_builder.tick()
        assert "did not move" in read(job_dir, "result.json")["error"]


def test_stage_jobs_are_never_published(stage_builder, stage_config, runner):
    job_dir = shipped_job(stage_builder, stage_config, runner)
    (job_dir / "publish.json").write_text(json.dumps({"patch_sha256": "0" * 64}))
    stage_builder.tick()
    assert "only patch builds" in read(job_dir, "published.json")["error"]
    assert not any("push" in a for a, _ in runner.calls)


class TestCheckProbeStages:
    def report(self, zb, *extra_env, **fields):
        return {
            "uid": 1000, "cap_eff": "0", "no_new_privs": "1", "token_seen": zb.PROBE_TOKEN,
            "env_names": ["PATH", "STAGE", "BRANCH", "ISSUE", "GITLAB_HOST", "GITHUB_REPO",
                          *extra_env],
            "host_mounts": [], "host_paths_visible": [], "writable_outside": [],
            "podman_socket": False, "workspace_writable": True, **fields,
        }  # fmt: skip

    def test_ship_with_both_credentials_authenticated_passes(self, zb):
        report = self.report(zb, "GITLAB_TOKEN", "GH_TOKEN", gitlab_user="z", github_user="b")
        assert zb.check_probe(report, "ship") == []

    def test_credential_that_does_not_authenticate_fails(self, zb):
        report = self.report(zb, "GITLAB_TOKEN", "GH_TOKEN", gitlab_user="", github_user="b")
        assert zb.check_probe(report, "ship") == ["the GitLab token did not authenticate"]

    def test_credential_a_stage_should_not_have_fails(self, zb):
        report = self.report(zb, "GITLAB_TOKEN", "GH_TOKEN", gitlab_user="z", github_user="b")
        [failure] = zb.check_probe(report, "propose")
        assert "GH_TOKEN" in failure

    def test_patch_builds_get_no_stage_variables(self, zb):
        [failure] = zb.check_probe(self.report(zb), "patch")
        assert "STAGE" in failure


def test_config_reads_stage_credentials(zb):
    config = zb.Config.from_env(
        {
            "ZEBRA_BUILDER_GITLAB_TOKEN": "a",
            "ZEBRA_BUILDER_GITLAB_MERGE_TOKEN": "b",
            "ZEBRA_BUILDER_GITHUB_TOKEN": "c",
            "CLAUDE_CODE_OAUTH_TOKEN": "t",
        }
    )
    assert (config.gitlab_token, config.gitlab_merge_token, config.github_token) == ("a", "b", "c")
    assert config.self_repo == "gidley/zebra" and config.github_repo == "bgidley/zebra"
    assert config.secrets() == ["t", "a", "b", "c"]
