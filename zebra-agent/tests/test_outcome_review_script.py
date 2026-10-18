"""scripts/zebra-outcome-review.sh: input building and exit codes (#192).

Runs the real script with a fake ``podman`` first on ``PATH``. The fake records
what the script sends to ``run_workflow`` and answers with a canned result, so the
script's two steps are tested as they run: building the workflow input, and
mapping the workflow's result to an exit code (0 complete, 2 awaiting a human
ruling, 1 anything else).
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "zebra-outcome-review.sh"
MAX_DIFF_CHARS = 60000

FAKE_PODMAN = """#!/usr/bin/env bash
case "$1" in
  inspect) echo "${FAKE_PODMAN_RUNNING:-true}" ;;
  exec)
    if [[ " $* " == *" run_workflow "* ]]; then
      printf '%s\\n' "$@" >"$FAKE_DIR/args.txt"
      if [[ " $* " == *" --input-file "* ]]; then cat >"$FAKE_DIR/stdin.json"; fi
      echo "fake run_workflow log line" >&2
      cat "$FAKE_DIR/out.txt"
    else
      echo abc1234
    fi
    ;;
esac
"""

OUTCOMES = "| # | Outcome | How we'll know |\n|---|---|---|\n| O1 | It works | A test |\n"
CLAUDE_REVIEW = {"verdicts": [{"id": "O1", "verdict": "met", "evidence": "x.py:1"}]}


@pytest.fixture
def fake(tmp_path: Path) -> Path:
    """A directory holding the fake podman, its canned output and what it recorded."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    podman = bin_dir / "podman"
    podman.write_text(FAKE_PODMAN)
    podman.chmod(0o755)
    (tmp_path / "out.txt").write_text("")
    return tmp_path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repo with a base commit tagged ``base``."""
    path = tmp_path / "repo"
    path.mkdir()
    _git(path, "init", "-q")
    (path / "a.txt").write_text("one\n")
    _git(path, "add", ".")
    _git(path, "commit", "-qm", "base")
    _git(path, "tag", "base")
    return path


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd,
        check=True,
    )


def _commit(repo: Path, name: str, content: str) -> None:
    (repo / name).write_text(content)
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", f"add {name}")


def _run(
    fake: Path, *args: str, cwd: Path | None = None, **env: str
) -> subprocess.CompletedProcess:
    full_env = {
        **os.environ,
        "PATH": f"{fake / 'bin'}{os.pathsep}{os.environ['PATH']}",
        "FAKE_DIR": str(fake),
        "ZEBRA_URL": "https://zebra.test",
        **env,
    }
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=cwd or fake,
        env=full_env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _status(fake: Path, result: dict | str) -> subprocess.CompletedProcess:
    raw = result if isinstance(result, str) else json.dumps(result)
    (fake / "out.txt").write_text(raw)
    return _run(fake, "status", "proc-1")


def _review_files(tmp_path: Path, claude: str | None = None) -> tuple[Path, Path]:
    outcomes = tmp_path / "outcomes.md"
    outcomes.write_text(OUTCOMES)
    review = tmp_path / "claude.json"
    review.write_text(claude if claude is not None else json.dumps(CLAUDE_REVIEW))
    return outcomes, review


def _run_review(fake: Path, repo: Path, tmp_path: Path, claude: str | None = None):
    outcomes, review = _review_files(tmp_path, claude)
    (fake / "out.txt").write_text(
        json.dumps({"status": "complete", "process_id": "p", "output": {"status": "agreed"}})
    )
    return _run(fake, "run", "192", "Script tests", str(outcomes), str(review), "base", cwd=repo)


# --- result handling (O1) ---------------------------------------------------


def test_complete_agreed_exits_0_and_prints_the_table(fake):
    result = _status(
        fake,
        {
            "status": "complete",
            "process_id": "proc-1",
            "output": {
                "status": "agreed",
                "table_markdown": "| O1 | met |",
                "followups": ["O2"],
            },
        },
    )

    assert result.returncode == 0, result.stdout
    assert "AGREED (process proc-1)" in result.stdout
    assert "| O1 | met |" in result.stdout
    assert "Follow-up issues needed for: O2" in result.stdout
    assert "Human ruling" not in result.stdout


def test_complete_ruled_exits_0_and_prints_the_ruling(fake):
    result = _status(
        fake,
        {
            "status": "complete",
            "process_id": "proc-1",
            "output": {
                "status": "ruled",
                "table_markdown": "| O1 | partial |",
                "ruling": "O1 is partial.",
                "disputed": ["O1"],
            },
        },
    )

    assert result.returncode == 0, result.stdout
    assert "RULED" in result.stdout
    assert "Human ruling:\nO1 is partial." in result.stdout
    assert "disputed outcomes: O1" in result.stdout


def test_awaiting_input_exits_2_with_task_link_and_poll_command(fake):
    result = _status(
        fake, {"status": "awaiting_input", "process_id": "proc-9", "task_id": "task-7"}
    )

    assert result.returncode == 2, result.stdout
    assert "BLOCKED" in result.stdout
    assert "Ruling task: https://zebra.test/tasks/task-7/" in result.stdout
    assert "Poll: bash scripts/zebra-outcome-review.sh status proc-9" in result.stdout


@pytest.mark.parametrize("status", ["failed", "running"])
def test_failed_or_still_running_exits_1(fake, status):
    result = _status(fake, {"status": status, "process_id": "proc-1", "error": "boom"})

    assert result.returncode == 1, result.stdout
    assert f"Review {status}: boom (process proc-1)" in result.stdout


def test_non_json_result_exits_1_with_output_and_log_tail(fake):
    result = _status(fake, "Traceback: something broke")

    assert result.returncode == 1, result.stdout
    assert "did not return JSON" in result.stdout
    assert "Traceback: something broke" in result.stdout
    assert "fake run_workflow log line" in result.stdout


def test_status_passes_the_process_id(fake):
    _status(fake, {"status": "running", "process_id": "proc-1"})

    args = (fake / "args.txt").read_text().split("\n")
    assert args[-3:-1] == ["--status", "proc-1"]


def test_unreachable_container_exits_1(fake):
    result = _run(fake, "status", "proc-1", FAKE_PODMAN_RUNNING="false")

    assert result.returncode == 1
    assert "unreachable" in result.stderr


def test_missing_arguments_exit_1_with_usage(fake):
    result = _run(fake, "run", "192")

    assert result.returncode == 1
    assert "zebra-outcome-review.sh run <issue>" in result.stderr


# --- input building (O2) ----------------------------------------------------


def test_run_sends_outcomes_claude_review_and_diff(fake, repo, tmp_path):
    _commit(repo, "b.txt", "new file\n")

    result = _run_review(fake, repo, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    sent = json.loads((fake / "stdin.json").read_text())
    assert sent["goal"] == "Outcome review of #192: Script tests"
    assert sent["issue"] == "192"
    assert sent["title"] == "Script tests"
    assert sent["outcomes"] == OUTCOMES
    assert sent["claude_review"] == CLAUDE_REVIEW
    assert sent["deployed_hash"] == "abc1234"
    assert "+new file" in sent["diff"]
    assert "a.txt" not in sent["diff"]
    args = (fake / "args.txt").read_text().split("\n")
    assert "Outcome Review" in args
    assert args[args.index("--model") + 1] == "sonnet"


def test_run_caps_the_diff(fake, repo, tmp_path):
    _commit(repo, "big.txt", "x" * (MAX_DIFF_CHARS * 2) + "\n")

    result = _run_review(fake, repo, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    diff = json.loads((fake / "stdin.json").read_text())["diff"]
    head, marker = diff[:MAX_DIFF_CHARS], diff[MAX_DIFF_CHARS:]
    assert head.startswith("diff --git a/big.txt")
    assert marker == (
        f"\n... diff truncated at {MAX_DIFF_CHARS} characters; read the source for the rest"
    )


def test_run_rejects_a_non_json_claude_review(fake, repo, tmp_path):
    result = _run_review(fake, repo, tmp_path, claude="O1: met")

    assert result.returncode == 1
    assert "is not JSON" in result.stderr
    assert not (fake / "stdin.json").exists()


def test_run_rejects_a_missing_claude_review(fake, repo, tmp_path):
    outcomes, _ = _review_files(tmp_path)

    result = _run(
        fake, "run", "192", "t", str(outcomes), str(tmp_path / "nope.json"), "base", cwd=repo
    )

    assert result.returncode == 1
    assert "No Claude review file" in result.stderr
    assert not (fake / "stdin.json").exists()
