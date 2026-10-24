"""Tests for the Git task actions (#64): behaviour against a local bare remote."""

import pytest

from vcs.helpers import make_task, sh_git
from zebra_tasks.vcs.actions import (
    GitBranchAction,
    GitCloneAction,
    GitCommitAction,
    GitDiffAction,
    GitPullAction,
    GitPushAction,
    GitStatusAction,
)


async def clone(workspace, remote, mock_context, **extra) -> str:
    result = await GitCloneAction().run(make_task({"url": str(remote), **extra}), mock_context)
    assert result.success, result.error
    return result.output["path"]


async def run(action, mock_context, **props):
    return await action.run(make_task(props), mock_context)


class TestClone:
    async def test_default_destination_per_process(self, workspace, remote, mock_context):
        result = await run(GitCloneAction(), mock_context, url=str(remote))

        assert result.success, result.error
        assert result.output["path"] == str(workspace / "test_process" / "origin")
        assert result.output["branch"] == "master"
        assert len(result.output["head"]) == 40
        assert mock_context.process.properties["repo"] == result.output
        assert (workspace / "test_process" / "origin" / "README.md").read_text() == "hello\n"

    async def test_explicit_dest_and_depth(self, workspace, remote, mock_context):
        result = await run(GitCloneAction(), mock_context, url=str(remote), dest="work", depth=1)

        assert result.success, result.error
        assert result.output["path"] == str(workspace / "work")

    async def test_non_empty_destination_refused(self, workspace, remote, mock_context):
        (workspace / "taken").mkdir()
        (workspace / "taken" / "file").write_text("x")

        result = await run(GitCloneAction(), mock_context, url=str(remote), dest="taken")

        assert not result.success
        assert "not empty" in result.error

    async def test_no_workspace_configured(self, mock_context):
        result = await run(GitCloneAction(), mock_context, url="https://gitlab.com/a/b.git")

        assert not result.success
        assert "ZEBRA_GIT_WORKSPACE" in result.error


class TestStatusAndDiff:
    async def test_clean_then_changed(self, workspace, remote, mock_context):
        path = await clone(workspace, remote, mock_context)

        clean = await run(GitStatusAction(), mock_context, repo_path=path)
        assert clean.success and clean.output["clean"] and clean.next_route == "clean"

        (workspace / "test_process/origin/README.md").write_text("changed\n")
        (workspace / "test_process/origin/new.txt").write_text("new\n")
        changed = await run(GitStatusAction(), mock_context, repo_path=path)

        assert changed.next_route == "changed"
        assert {f["path"]: f["status"] for f in changed.output["files"]} == {
            "README.md": "M",
            "new.txt": "??",
        }

    async def test_diff_includes_untracked_and_leaves_them_untracked(
        self, workspace, remote, mock_context
    ):
        path = await clone(workspace, remote, mock_context)
        (workspace / "test_process/origin/README.md").write_text("changed\n")
        (workspace / "test_process/origin/new.txt").write_text("brand new\n")

        result = await run(GitDiffAction(), mock_context, repo_path=path)

        assert result.success, result.error
        assert "+changed" in result.output["diff"]
        assert "+brand new" in result.output["diff"]
        assert "2 files changed" in result.output["stat"]
        assert result.output["truncated"] is False
        status = sh_git("status", "--porcelain", cwd=workspace / "test_process/origin")
        assert "?? new.txt" in status

    async def test_diff_truncated(self, workspace, remote, mock_context):
        path = await clone(workspace, remote, mock_context)
        (workspace / "test_process/origin/README.md").write_text("x" * 500 + "\n")

        result = await run(GitDiffAction(), mock_context, repo_path=path, max_chars=50)

        assert len(result.output["diff"]) == 50
        assert result.output["truncated"] is True


class TestBranchCommit:
    async def test_create_branch_and_commit_with_identity(
        self, workspace, remote, mock_context, monkeypatch
    ):
        monkeypatch.setenv("ZEBRA_GIT_AUTHOR_NAME", "Zebra Bot")
        monkeypatch.setenv("ZEBRA_GIT_AUTHOR_EMAIL", "bot@zebra.test")
        path = await clone(workspace, remote, mock_context)
        branch = await run(
            GitBranchAction(), mock_context, repo_path=path, name="zebra/x", create=True
        )
        assert branch.success and branch.output["branch"] == "zebra/x"

        (workspace / "test_process/origin/notes.md").write_text("note\n")
        result = await run(GitCommitAction(), mock_context, repo_path=path, message="Add notes")

        assert result.success, result.error
        assert result.next_route == "committed"
        assert result.output["files"] == ["notes.md"]
        log = sh_git("log", "-1", "--format=%an <%ae>|%s", cwd=workspace / "test_process/origin")
        assert log.strip() == "Zebra Bot <bot@zebra.test>|Add notes"

    async def test_nothing_to_commit(self, workspace, remote, mock_context):
        path = await clone(workspace, remote, mock_context)

        result = await run(GitCommitAction(), mock_context, repo_path=path, message="noop")

        assert result.success
        assert result.output["committed"] is False
        assert result.next_route == "nothing_to_commit"

    async def test_commit_only_given_paths(self, workspace, remote, mock_context):
        path = await clone(workspace, remote, mock_context)
        (workspace / "test_process/origin/a.txt").write_text("a\n")
        (workspace / "test_process/origin/b.txt").write_text("b\n")

        result = await run(
            GitCommitAction(), mock_context, repo_path=path, message="a only", paths=["a.txt"]
        )

        assert result.output["files"] == ["a.txt"]

    async def test_repo_hooks_do_not_run(self, workspace, remote, mock_context):
        path = await clone(workspace, remote, mock_context)
        hook = workspace / "test_process/origin/.git/hooks/pre-commit"
        marker = workspace / "hook-ran"
        hook.write_text(f"#!/bin/sh\ntouch {marker}\n")
        hook.chmod(0o755)
        (workspace / "test_process/origin/c.txt").write_text("c\n")

        result = await run(GitCommitAction(), mock_context, repo_path=path, message="c")

        assert result.success
        assert not marker.exists()


class TestPushPull:
    async def test_push_feature_branch(self, workspace, remote, mock_context):
        path = await clone(workspace, remote, mock_context)
        await run(GitBranchAction(), mock_context, repo_path=path, name="feature", create=True)
        (workspace / "test_process/origin/f.txt").write_text("f\n")
        commit = await run(GitCommitAction(), mock_context, repo_path=path, message="Feature")

        result = await run(GitPushAction(), mock_context, repo_path=path)

        assert result.success, result.error
        assert result.output == {
            "remote": "origin",
            "branch": "feature",
            "head": commit.output["sha"],
        }
        assert sh_git("rev-parse", "feature", cwd=remote).strip() == commit.output["sha"]

    async def test_protected_branch_refused_unless_allowed(self, workspace, remote, mock_context):
        path = await clone(workspace, remote, mock_context)
        (workspace / "test_process/origin/m.txt").write_text("m\n")
        commit = await run(GitCommitAction(), mock_context, repo_path=path, message="On master")

        refused = await run(GitPushAction(), mock_context, repo_path=path)
        assert not refused.success
        assert "protected" in refused.error
        assert sh_git("rev-parse", "master", cwd=remote).strip() != commit.output["sha"]

        allowed = await run(GitPushAction(), mock_context, repo_path=path, allow_protected=True)
        assert allowed.success, allowed.error
        assert sh_git("rev-parse", "master", cwd=remote).strip() == commit.output["sha"]

    async def test_non_fast_forward_push_fails(self, workspace, remote, seed, mock_context):
        path = await clone(workspace, remote, mock_context)
        (seed / "other.txt").write_text("other\n")
        sh_git("add", "other.txt", cwd=seed)
        sh_git("commit", "-m", "Remote moved", cwd=seed)
        sh_git("push", "origin", "master", cwd=seed)
        (workspace / "test_process/origin/mine.txt").write_text("mine\n")
        await run(GitCommitAction(), mock_context, repo_path=path, message="Diverged")

        result = await run(GitPushAction(), mock_context, repo_path=path, allow_protected=True)

        assert not result.success
        assert "git push failed" in result.error

    async def test_pull_fast_forwards(self, workspace, remote, seed, mock_context):
        path = await clone(workspace, remote, mock_context)
        (seed / "later.txt").write_text("later\n")
        sh_git("add", "later.txt", cwd=seed)
        sh_git("commit", "-m", "Later", cwd=seed)
        sh_git("push", "origin", "master", cwd=seed)

        result = await run(GitPullAction(), mock_context, repo_path=path)

        assert result.success, result.error
        assert result.output["updated"] is True
        assert (workspace / "test_process/origin/later.txt").exists()


def test_reversibility_hints():
    for action in (
        GitCloneAction,
        GitStatusAction,
        GitDiffAction,
        GitBranchAction,
        GitCommitAction,
        GitPullAction,
    ):
        assert action.get_metadata().reversibility_hint == "always_reversible"
    assert GitPushAction.get_metadata().reversibility_hint == "always_irreversible"


def test_push_has_no_force_option():
    names = {p.name for p in GitPushAction.inputs}
    assert not names & {"force", "force_with_lease", "refspec"}


@pytest.mark.parametrize("name", ["-D", "bad..name", "with space"])
async def test_invalid_branch_names_refused(name, workspace, remote, mock_context):
    path = await clone(workspace, remote, mock_context)

    result = await run(GitBranchAction(), mock_context, repo_path=path, name=name, create=True)

    assert not result.success
