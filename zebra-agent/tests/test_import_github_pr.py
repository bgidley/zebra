"""Tests for scripts/import_github_pr.py (#282 slice D). No real GitHub or GitLab is touched."""

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from zebra_agent.commons import keys

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "import_github_pr.py"
spec = importlib.util.spec_from_file_location("import_github_pr", SCRIPT)
imp = importlib.util.module_from_spec(spec)
sys.modules["import_github_pr"] = imp
spec.loader.exec_module(imp)

SHA = "a" * 40


def signed_body(sha: str = SHA, repo: str = "bgidley/zebra", secret: str | None = None) -> str:
    secret = secret or keys.generate_secret_key()
    npub = keys.npub_encode(keys.public_key(secret))
    sig = keys.sign(secret, imp.origin_message(repo, sha))
    return f"Fix thing\n\n<!-- zebra-origin\nnpub: {npub}\nhead: {sha}\nsig: {sig}\n-->\n"


def test_valid_origin_verifies():
    origin = imp.verify_origin(signed_body(), SHA)
    assert origin.head == SHA


@pytest.mark.parametrize(
    "body, head, why",
    [
        ("no statement", SHA, "no zebra-origin"),
        (signed_body(), "b" * 40, "different head"),
        (signed_body(repo="other/repo"), SHA, "does not verify"),
        (signed_body().replace("sig: ", "sig: 00"), SHA, "malformed"),
        (signed_body().replace("npub1", "npub2"), SHA, "invalid|does not verify"),
        ("<!-- zebra-origin\nnpub: x\n-->", SHA, "malformed|no zebra-origin"),
    ],
)
def test_bad_origin_refused(body, head, why):
    with pytest.raises(imp.Refused, match=why):
        imp.verify_origin(body, head)


def test_builtin_scan_rejects_secret_and_blocked_path():
    """The fallback scan (used only if slice A's scanner is missing)."""
    patch = "+++ b/x.py\n+token = 'ghp_" + "a" * 36 + "'\n+mail = 'jane.doe@gmail.com'\n"
    scan = imp.builtin_scan(
        patch,
        paths=["x.py", ".env", "deploy/a.sh"],
        commit_messages=[],
        author_emails=[],
        pr_body="",
    )
    kinds = {f["kind"] for f in scan.findings}
    assert scan.verdict == "rejected"
    assert {"blocked_path", "sensitive_path"} <= kinds
    assert len(scan.findings) >= 3  # secret and email found as well


def test_builtin_scan_clean_diff_passes():
    scan = imp.builtin_scan(
        "+++ b/a.py\n+x = 1\n",
        paths=["a.py"],
        commit_messages=["feat: x"],
        author_emails=[],
        pr_body="ok",
    )
    assert scan.verdict == "clean"


def _git_diff(path: str, *lines: str) -> str:
    return (
        f"diff --git a/{path} b/{path}\nnew file mode 100644\n--- /dev/null\n+++ b/{path}\n"
        f"@@ -0,0 +1,{len(lines)} @@\n" + "".join(f"+{line}\n" for line in lines)
    )


def test_scan_uses_slice_a_scanner():
    from zebra_tasks.contribute import diff_scan

    assert hasattr(diff_scan, "scan_diff_text")
    patch = _git_diff("x.py", "token = 'ghp_" + "aB3" * 12 + "'", "mail = 'jane.doe@gmail.com'")
    patch += _git_diff(".env", "A=1")
    patch += _git_diff("deploy/a.sh", "echo hi")
    scan = imp.scan_diff(
        patch,
        paths=["x.py", ".env", "deploy/a.sh"],
        commit_messages=[],
        author_emails=[],
        pr_body="",
    )
    kinds = {f["kind"] for f in scan.findings}
    assert scan.verdict == "rejected"
    assert {"secret", "email", "blocked_file", "sensitive_path"} <= kinds


def test_scan_sensitive_path_alone_rejects():
    scan = imp.scan_diff(
        _git_diff(".gitlab-ci.yml", "stages: [lint]"),
        paths=[".gitlab-ci.yml"],
        commit_messages=["ci: x"],
        author_emails=["42+octo@users.noreply.github.com"],
        pr_body="ok",
    )
    assert scan.verdict == "rejected"
    assert [f["kind"] for f in scan.findings] == ["sensitive_path"]


def test_scan_clean_diff_passes():
    scan = imp.scan_diff(
        _git_diff("a.py", "x = 1"),
        paths=["a.py"],
        commit_messages=["feat: x\n\nSigned-off-by: Octo <42+octo@users.noreply.github.com>"],
        author_emails=["42+octo@users.noreply.github.com"],
        pr_body="ok",
    )
    assert scan.verdict == "clean", scan.findings


def test_scan_real_author_email_rejects():
    scan = imp.scan_diff(
        _git_diff("a.py", "x = 1"),
        paths=["a.py"],
        commit_messages=["feat: x"],
        author_emails=["jane.doe@gmail.com"],
        pr_body="ok",
    )
    assert scan.verdict == "rejected"


def test_scan_error_fails_closed(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("llm down")

    monkeypatch.setattr(imp, "builtin_scan", boom)
    scan = imp.scan_diff("", paths=[], commit_messages=[], author_emails=[], pr_body="")
    assert scan.verdict == "rejected"


# ------------------------------------------------ flow against local repos + fake gh


def vc(cwd, *cmd):
    return subprocess.run(
        ["git", "-c", "user.name=T", "-c", "user.email=t@example.com", *cmd],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A clone with remotes origin (GitLab) and github, and a PR head at refs/pull/7/head."""
    gl, gh, work = tmp_path / "gl.git", tmp_path / "gh.git", tmp_path / "work"
    vc(tmp_path, "init", "--bare", "-b", "master", str(gl))
    vc(tmp_path, "init", "--bare", "-b", "master", str(gh))
    vc(tmp_path, "clone", str(gl), str(work))
    (work / "a.py").write_text("x = 1\n")
    vc(work, "add", ".")
    vc(work, "commit", "-m", "base")
    vc(work, "push", "origin", "HEAD:master")
    vc(work, "remote", "add", "github", str(gh))
    vc(work, "checkout", "-b", "pr")
    (work / "a.py").write_text("x = 2\n")
    vc(work, "commit", "-am", "contributor change", "--author=Con <con@users.noreply.github.com>")
    head = vc(work, "rev-parse", "HEAD").strip()
    vc(work, "push", "github", "HEAD:refs/pull/7/head")
    vc(work, "checkout", "master")
    vc(work, "fetch", "origin")
    monkeypatch.chdir(work)
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    return work, gl, head


def fake_runner(pr_json):
    def runner(cmd):
        if cmd[0] == "gh" and cmd[1] == "api":
            return json.dumps(pr_json)
        if cmd[0] == "gh":
            runner.calls.append(cmd)
            return ""
        return imp.run(cmd)

    runner.calls = []
    return runner


def pr_json(head, body):
    return {
        "title": "Fix X",
        "body": body,
        "state": "open",
        "user": {"login": "con"},
        "head": {"sha": head},
    }


def args(**kw):
    return argparse.Namespace(pr=7, slug=None, allow_unsigned=False, **kw)


def test_prepare_creates_local_branch_and_does_not_push(world, capsys):
    work, gl, head = world
    runner = fake_runner(pr_json(head, signed_body(head)))
    assert imp.cmd_prepare(args(), runner) == 0
    assert vc(work, "rev-parse", "f7/gh7-fix-x").strip() == head
    assert vc(gl, "branch", "--list", "f7/*").strip() == ""  # nothing pushed, so no CI
    assert "NOT pushed" in capsys.readouterr().out


def test_prepare_refuses_unsigned_unless_allowed(world):
    _, _, head = world
    runner = fake_runner(pr_json(head, "no statement"))
    with pytest.raises(imp.Refused):
        imp.cmd_prepare(args(), runner)
    a = args()
    a.allow_unsigned = True
    assert imp.cmd_prepare(a, runner) == 0


def test_push_requires_the_reviewed_sha_and_keeps_author(world):
    _, gl, head = world
    runner = fake_runner(pr_json(head, signed_body(head)))
    with pytest.raises(imp.Refused, match="reviewed sha"):
        imp.cmd_push(args(reviewed_sha="c" * 40), runner)
    assert vc(gl, "branch", "--list", "f7/*").strip() == ""
    assert imp.cmd_push(args(reviewed_sha=head), runner) == 0
    assert vc(gl, "rev-parse", "f7/gh7-fix-x").strip() == head
    author = vc(gl, "log", "-1", "--format=%an <%ae>", head).strip()
    assert author == "Con <con@users.noreply.github.com>"


def test_push_refuses_when_pr_moved_after_review(world):
    _, gl, head = world
    runner = fake_runner(pr_json("d" * 40, signed_body("d" * 40)))
    with pytest.raises(imp.Refused, match="differs from the API head"):
        imp.cmd_push(args(reviewed_sha=head), runner)
    assert vc(gl, "branch", "--list", "f7/*").strip() == ""


def test_rejected_scan_blocks_prepare(world):
    work, _, _ = world
    vc(work, "checkout", "pr")
    (work / ".env").write_text("K=1\n")
    vc(work, "add", ".")
    vc(work, "commit", "-m", "oops")
    head = vc(work, "rev-parse", "HEAD").strip()
    vc(work, "push", "github", "HEAD:refs/pull/7/head", "-f")
    vc(work, "checkout", "master")
    runner = fake_runner(pr_json(head, signed_body(head)))
    with pytest.raises(imp.Refused, match="scan rejected"):
        imp.cmd_prepare(args(), runner)
    assert vc(work, "branch", "--list", "f7/*").strip() == ""


def test_reject_closes_with_comment():
    runner = fake_runner({})
    imp.cmd_reject(argparse.Namespace(pr=7, reason="not now"), runner)
    assert runner.calls[0][:3] == ["gh", "pr", "close"] and "not now" in runner.calls[0]
