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

    def __call__(self, args, *, cwd=None, env=None, timeout=None):
        args = list(args)
        self.calls.append((args, dict(env or {})))
        ok = subprocess.CompletedProcess(args, 0, "", "")
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
