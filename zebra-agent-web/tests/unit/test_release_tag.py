"""Tests for scripts/release_tag.py and the version in scripts/gen_version.py (#283).

Each test builds a small real git repository, so tag lookup, commit ranges and
``git describe`` run as they do in CI. A fake GitLab API records every call.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
CI_FILE = SCRIPTS.parent / ".gitlab-ci.yml"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rt():
    return _load("release_tag")


@pytest.fixture(scope="module")
def gv():
    return _load("gen_version")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A repo with one tagged release (v0.2.0) and three commits after it."""
    path = tmp_path / "repo"
    path.mkdir()
    _git(path, "init", "-q", "-b", "master")
    _git(path, "config", "user.email", "t@example.com")
    _git(path, "config", "user.name", "Test")
    _git(path, "config", "commit.gpgsign", "false")
    _git(path, "config", "tag.gpgsign", "false")

    def commit(message: str) -> str:
        _git(path, "commit", "-q", "--allow-empty", "-m", message)
        return _git(path, "rev-parse", "HEAD")

    commit("feat: old work\n\nCloses #1")
    _git(path, "tag", "v0.2.0")
    _git(path, "tag", "not-a-release")
    commit("feat: ethics gate\n\nPart of #10")
    commit("Merge f10/ethics — Closes #10")
    commit("fix: escape output\n\nFixes #12, resolves #13")
    monkeypatch.chdir(path)
    return path


class FakeApi:
    def __init__(self, head: str, issues: dict[int, dict] | None = None, tag_exists=False):
        self.head = head
        self.issues = issues or {}
        self.tag_exists = tag_exists
        self.calls: list[tuple[str, str, dict | None]] = []

    def __call__(self, method, path, body=None):
        self.calls.append((method, path, body))
        if path.endswith("/repository/branches/master"):
            return 200, {"commit": {"id": self.head}}
        if "/repository/tags/" in path:
            return (200, {}) if self.tag_exists else (404, None)
        if "/issues/" in path:
            iid = int(path.rsplit("/", 1)[1])
            return (200, self.issues[iid]) if iid in self.issues else (404, None)
        if method == "POST" and path.endswith("/releases"):
            return 201, {"_links": {"self": "https://gitlab.example/releases/v"}}
        return 404, None

    @property
    def posted(self):
        return [body for method, path, body in self.calls if method == "POST"]


MASTER_ENV = {
    "CI_COMMIT_BRANCH": "master",
    "CI_DEFAULT_BRANCH": "master",
    "CI_PIPELINE_SOURCE": "push",
}


def _args(rt, ref: str, **overrides) -> argparse.Namespace:
    args = rt.build_parser({}).parse_args(["--ref", ref, "--no-fetch"])
    for key, value in overrides.items():
        setattr(args, key, value)
    return args


def _issue(title: str, state: str = "closed", labels=()) -> dict:
    return {"title": title, "state": state, "labels": list(labels), "web_url": "u"}


# --- versions --------------------------------------------------------------------------------


class TestVersions:
    def test_bumps(self, rt):
        assert rt.next_version("v0.2.0", "minor", None) == "0.3.0"
        assert rt.next_version("v0.2.5", "patch", None) == "0.2.6"
        assert rt.next_version("v0.2.5", "major", None) == "1.0.0"

    def test_first_release_is_0_1_0(self, rt):
        assert rt.next_version(None, "minor", None) == "0.1.0"

    def test_explicit_version_must_be_above_previous(self, rt):
        assert rt.next_version("v0.2.0", "minor", "v1.0.0") == "1.0.0"
        with pytest.raises(rt.ReleaseError, match="not above"):
            rt.next_version("v0.2.0", "minor", "0.2.0")

    def test_latest_tag_is_by_semver_not_text(self, rt):
        assert rt.latest_tag(["v0.9.0", "v0.10.0", "v0.2.0", "nightly", "v1.0"]) == "v0.10.0"
        assert rt.latest_tag(["nightly"]) is None

    def test_rejects_non_semver(self, rt):
        with pytest.raises(rt.ReleaseError):
            rt.parse_version("1.2")


# --- notes -----------------------------------------------------------------------------------


class TestNotes:
    def test_closed_issues_since_last_tag_only(self, rt, repo):
        commits = rt.commits_between("v0.2.0", "HEAD")
        refs = rt.closed_issue_refs(commits)
        assert list(refs) == [10, 12, 13]  # #1 predates the tag; "Part of" does not close
        assert refs[10] == "Merge f10/ethics — Closes #10"

    def test_open_issues_are_dropped_and_security_listed_first(self, rt):
        issues = {
            10: _issue("Ethics gate"),
            12: _issue("Escape output", labels=["security"]),
            13: _issue("Still open", state="opened"),
        }
        fetch = rt.issue_fetcher(FakeApi("x", issues), "gidley/zebra")
        found = rt.resolve_issues({10: "a", 12: "b", 13: "c"}, fetch)
        notes = rt.render_notes("0.3.0", "v0.2.0", 3, found)
        assert "#13" not in notes
        assert notes.index("### Security") < notes.index("- #12 Escape output")
        assert notes.index("- #12") < notes.index("### Closed issues") < notes.index("- #10")
        assert "3 commits since v0.2.0." in notes

    def test_without_api_uses_commit_subjects(self, rt):
        found = rt.resolve_issues({7: "feat: thing — Closes #7"}, None)
        assert found[0].title == "feat: thing — Closes #7"


# --- cutting the release -----------------------------------------------------------------------


class TestRelease:
    def test_creates_release_at_ref_from_green_master(self, rt, repo, tmp_path):
        head = _git(repo, "rev-parse", "HEAD")
        api = FakeApi(head, {10: _issue("Ethics gate"), 12: _issue("Fix"), 13: _issue("More")})
        notes_file = tmp_path / "notes.md"
        notes = rt.run(_args(rt, head, notes_file=str(notes_file)), MASTER_ENV, api)

        (body,) = api.posted
        assert body["tag_name"] == "v0.3.0"
        assert body["ref"] == head
        assert body["description"] == notes == notes_file.read_text()
        assert "- #10 Ethics gate" in notes

    @pytest.mark.parametrize(
        "env",
        [
            {**MASTER_ENV, "CI_COMMIT_BRANCH": "f10/ethics"},
            {**MASTER_ENV, "CI_PIPELINE_SOURCE": "web"},
            {**MASTER_ENV, "CI_COMMIT_BRANCH": ""},  # a tag pipeline has no branch
        ],
    )
    def test_refuses_anything_but_a_master_push_pipeline(self, rt, repo, env):
        head = _git(repo, "rev-parse", "HEAD")
        api = FakeApi(head)
        with pytest.raises(rt.ReleaseError, match="only from a master push"):
            rt.run(_args(rt, head), env, api)
        assert api.posted == []

    def test_refuses_a_stale_pipeline(self, rt, repo):
        old = _git(repo, "rev-parse", "HEAD~1")
        api = FakeApi(head=_git(repo, "rev-parse", "HEAD"))
        with pytest.raises(rt.ReleaseError, match="no longer the head"):
            rt.run(_args(rt, old), MASTER_ENV, api)
        assert api.posted == []

    def test_refuses_an_existing_tag(self, rt, repo):
        head = _git(repo, "rev-parse", "HEAD")
        api = FakeApi(head, tag_exists=True)
        with pytest.raises(rt.ReleaseError, match="already exists"):
            rt.run(_args(rt, head), MASTER_ENV, api)
        assert api.posted == []

    def test_needs_a_token(self, rt, repo):
        with pytest.raises(rt.ReleaseError, match="RELEASE_GITLAB_TOKEN"):
            rt.run(_args(rt, "HEAD"), MASTER_ENV, None)

    def test_dry_run_changes_nothing_and_needs_no_token(self, rt, repo, capsys):
        notes = rt.run(_args(rt, "HEAD", dry_run=True), {}, None)
        assert "Would release v0.3.0" in capsys.readouterr().out
        assert "- #10 Merge f10/ethics" in notes

    def test_main_exits_1_with_reason(self, rt, repo, monkeypatch, capsys):
        monkeypatch.delenv("RELEASE_GITLAB_TOKEN", raising=False)
        for key, value in MASTER_ENV.items():
            monkeypatch.setenv(key, value)
        assert rt.main(["--ref", "HEAD", "--no-fetch"]) == 1
        assert "RELEASE_GITLAB_TOKEN" in capsys.readouterr().err


class TestCiJob:
    def test_release_tag_job_is_manual_master_only_and_last(self):
        yaml = pytest.importorskip("yaml")
        ci = yaml.safe_load(CI_FILE.read_text())
        assert ci["stages"][-1] == "release"
        job = ci["release:tag"]
        assert job["stage"] == "release"
        (rule,) = job["rules"]
        assert rule["if"] == '$CI_COMMIT_BRANCH == "master" && $CI_PIPELINE_SOURCE == "push"'
        assert rule["when"] == "manual"
        assert rule["allow_failure"] is True
        # The deploy job is untouched: still master push only.
        assert ci["deploy"]["rules"] == [
            {"if": '$CI_COMMIT_BRANCH == "master" && $CI_PIPELINE_SOURCE == "push"'}
        ]


# --- gen_version ---------------------------------------------------------------------------


class TestGenVersion:
    @pytest.mark.parametrize(
        ("describe", "expected"),
        [
            ("v0.3.0-0-gabc1234", "0.3.0"),
            ("v0.3.0-4-gabc1234", "0.3.0+4.gabc1234"),
            (None, "0.0.0+gdef5678"),
            ("weird", "0.0.0+gdef5678"),
        ],
    )
    def test_version_from_describe(self, gv, describe, expected):
        assert gv.version_from_describe(describe, "def5678") == expected

    def _run(self, repo: Path) -> dict:
        out = subprocess.run(
            [sys.executable, str(SCRIPTS / "gen_version.py")],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        return json.loads(out)

    def test_version_after_a_tag(self, repo):
        data = self._run(repo)
        short = _git(repo, "rev-parse", "--short", "HEAD")
        assert data["version"] == f"0.2.0+3.g{short}"
        assert data["short_hash"] == short
        assert len(data["commits"]) == 4

    def test_version_on_a_tag(self, repo):
        _git(repo, "tag", "v0.3.0")
        assert self._run(repo)["version"] == "0.3.0"

    def test_version_before_any_release(self, repo):
        _git(repo, "tag", "-d", "v0.2.0")
        short = _git(repo, "rev-parse", "--short", "HEAD")
        assert self._run(repo)["version"] == f"0.0.0+g{short}"
