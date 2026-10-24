"""Leak-vector matrix for the Git task actions (#64): sandbox, remotes, config, credentials."""

import pytest

from vcs.helpers import make_task, sh_git
from zebra_tasks.vcs.actions import (
    GitBranchAction,
    GitCloneAction,
    GitCommitAction,
    GitPullAction,
    GitPushAction,
    GitStatusAction,
)
from zebra_tasks.vcs.base import _ENV_ALLOWLIST, GitActionError, GitRunner, check_remote


async def clone(workspace, remote, mock_context) -> str:
    result = await GitCloneAction().run(make_task({"url": str(remote)}), mock_context)
    assert result.success, result.error
    return result.output["path"]


class TestRemotes:
    @pytest.mark.parametrize(
        "url",
        [
            "https://gitlab.com/gidley/zebra.git",
            "ssh://git@gitlab.com/gidley/zebra.git",
            "git@gitlab.com:gidley/zebra.git",
        ],
    )
    def test_allowed(self, url, tmp_path):
        assert check_remote(url, tmp_path) == url

    @pytest.mark.parametrize(
        "url",
        [
            "--upload-pack=touch /tmp/pwned",
            "-oProxyCommand=x",
            "ext::sh -c touch% /tmp/pwned",
            "file:///etc",
            "http://example.com/repo.git",
            "/etc",
            "relative/path",
            "",
        ],
    )
    async def test_clone_refused(self, url, workspace, mock_context):
        result = await GitCloneAction().run(make_task({"url": url}), mock_context)

        assert not result.success
        assert not any((workspace / "test_process").glob("*"))

    async def test_local_path_outside_workspace_refused(self, workspace, tmp_path, mock_context):
        outside = tmp_path / "elsewhere.git"
        outside.mkdir()

        result = await GitCloneAction().run(make_task({"url": str(outside)}), mock_context)

        assert not result.success

    @pytest.mark.parametrize("action", [GitPushAction, GitPullAction])
    async def test_raw_url_remote_refused(self, action, workspace, remote, mock_context):
        path = await clone(workspace, remote, mock_context)

        result = await action().run(
            make_task(
                {"repo_path": path, "remote": "https://evil.example/x.git", "branch": "feature"}
            ),
            mock_context,
        )

        assert not result.success
        assert "Unknown remote" in result.error


class TestWorkspaceSandbox:
    @pytest.mark.parametrize("repo_path", ["../outside", "/etc", "/"])
    async def test_repo_path_escape_refused(self, repo_path, workspace, mock_context):
        result = await GitStatusAction().run(make_task({"repo_path": repo_path}), mock_context)

        assert not result.success
        assert "Security error" in result.error

    @pytest.mark.parametrize("override", ["/", "/etc", "../"])
    async def test_workspace_property_cannot_escape_env_root(
        self, override, workspace, remote, mock_context
    ):
        result = await GitCloneAction().run(
            make_task({"url": str(remote), "workspace": override, "dest": "x"}), mock_context
        )

        assert not result.success
        assert "Security error" in result.error

    async def test_workspace_property_narrows_env_root(self, workspace, remote, mock_context):
        result = await GitCloneAction().run(
            make_task({"url": str(remote), "workspace": "team", "dest": "x"}), mock_context
        )

        assert not result.success  # the remote is now outside the narrowed workspace
        assert "outside" in result.error

    async def test_clone_dest_escape_refused(self, workspace, remote, mock_context):
        result = await GitCloneAction().run(
            make_task({"url": str(remote), "dest": "../escaped"}), mock_context
        )

        assert not result.success
        assert not (workspace.parent / "escaped").exists()

    async def test_commit_path_option_refused(self, workspace, remote, mock_context):
        path = await clone(workspace, remote, mock_context)

        result = await GitCommitAction().run(
            make_task({"repo_path": path, "message": "x", "paths": ["--all"]}), mock_context
        )

        assert not result.success


class TestRepoConfig:
    @pytest.mark.parametrize(
        "snippet",
        [
            "[core]\n\tfsmonitor = touch {marker}\n",
            "[core]\n\tsshCommand = touch {marker}\n",
            '[filter "x"]\n\tclean = touch {marker}\n',
            '[url "https://evil.example/"]\n\tinsteadOf = /\n',
            "[include]\n\tpath = /tmp/other.config\n",
            '[remote "evil"]\n\turl = ext::sh -c touch% {marker}\n',
        ],
    )
    async def test_edited_config_refused(self, snippet, workspace, remote, mock_context):
        path = await clone(workspace, remote, mock_context)
        marker = workspace / "config-ran"
        config = workspace / "test_process/origin/.git/config"
        config.write_text(config.read_text() + snippet.format(marker=marker))

        result = await GitStatusAction().run(make_task({"repo_path": path}), mock_context)

        assert not result.success
        assert "unsupported config key" in result.error or "Remote not allowed" in result.error
        assert not marker.exists()


class TestCredentials:
    def test_header_scoped_to_configured_hosts(self, tmp_path):
        runner = GitRunner(workspace=tmp_path, token="s3cret", token_hosts=["gitlab.com"])

        env = runner.env()

        keys = {
            env[k]: env[k.replace("KEY", "VALUE")] for k in env if k.startswith("GIT_CONFIG_KEY_")
        }
        assert "http.https://gitlab.com/.extraHeader" in keys
        assert keys["http.https://gitlab.com/.extraHeader"].startswith("Authorization: Basic ")
        assert "http.extraHeader" not in keys
        assert not any("s3cret" in v for v in env.values())

    async def test_header_visible_only_for_scoped_host_and_redacted(self, workspace):
        runner = GitRunner(workspace=workspace, token="s3cret", token_hosts=["gitlab.com"])

        scoped = await runner.run(
            ["config", "--get-urlmatch", "http.extraHeader", "https://gitlab.com/a/b.git"],
            workspace,
            check=False,
        )
        other = await runner.run(
            ["config", "--get-urlmatch", "http.extraHeader", "https://evil.example/a/b.git"],
            workspace,
            check=False,
        )

        assert scoped.stdout.strip() == "Authorization: Basic ***"
        assert other.stdout.strip() == ""

    async def test_token_never_in_argv(self, workspace, remote, mock_context, monkeypatch):
        import asyncio

        monkeypatch.setenv("ZEBRA_GIT_TOKEN", "s3cret")
        seen: list[tuple] = []
        real = asyncio.create_subprocess_exec

        async def spy(*args, **kwargs):
            seen.append(args)
            return await real(*args, **kwargs)

        monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)
        await clone(workspace, remote, mock_context)

        assert seen
        assert not any("s3cret" in str(arg) for argv in seen for arg in argv)

    async def test_error_output_redacted(self, workspace):
        runner = GitRunner(workspace=workspace, token="s3cret", token_hosts=["gitlab.com"])
        runner.env()

        with pytest.raises(GitActionError) as err:
            await runner.run(["rev-parse", "--verify", "s3cret"], workspace)

        assert "s3cret" not in str(err.value)

    async def test_other_secret_env_refused(self, workspace, remote, mock_context, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-secret")

        result = await GitCloneAction().run(
            make_task({"url": str(remote), "token_env": "OPENROUTER_API_KEY"}), mock_context
        )

        assert not result.success
        assert "ZEBRA_GIT_TOKEN" in result.error

    async def test_timeout_fails_cleanly(self, workspace, remote, mock_context):
        path = await clone(workspace, remote, mock_context)

        result = await GitStatusAction().run(
            make_task({"repo_path": path, "timeout": 0.000001}), mock_context
        )

        assert not result.success
        assert "timed out" in result.error


class TestLocalRemotes:
    """#241: on local transport git runs the other repository's helpers without our hardening."""

    @pytest.fixture
    def evil_remote(self, workspace, remote):
        """The seeded remote, armed to run a command on fetch and on push."""
        marker = workspace.parent / "PWNED"
        with open(remote / "config", "a") as f:
            f.write(f'[core]\n\talternateRefsCommand = "env > {marker}; :"\n')
        hook = remote / "hooks" / "pre-receive"
        hook.write_text(f"#!/bin/sh\nenv > {marker}\n")
        hook.chmod(0o755)
        return remote, marker

    def test_local_remote_refused_by_default(self, workspace, monkeypatch):
        monkeypatch.delenv("ZEBRA_GIT_ALLOW_LOCAL_REMOTES")

        with pytest.raises(GitActionError, match="Remote not allowed"):
            check_remote(str(workspace / "remotes" / "origin.git"), workspace)

    async def test_evil_local_remote_cannot_be_cloned(self, evil_remote, monkeypatch, mock_context):
        remote, marker = evil_remote
        monkeypatch.delenv("ZEBRA_GIT_ALLOW_LOCAL_REMOTES")

        result = await GitCloneAction().run(make_task({"url": str(remote)}), mock_context)

        assert not result.success
        assert "Remote not allowed" in result.error
        assert not marker.exists()

    async def test_repo_pointing_at_local_path_cannot_push(
        self, workspace, evil_remote, monkeypatch, mock_context
    ):
        remote, marker = evil_remote
        path = await clone(workspace, remote, mock_context)  # allowed while the flag is on
        marker.unlink(missing_ok=True)
        await GitBranchAction().run(
            make_task({"repo_path": path, "name": "feature", "create": True}), mock_context
        )
        monkeypatch.delenv("ZEBRA_GIT_ALLOW_LOCAL_REMOTES")

        result = await GitPushAction().run(make_task({"repo_path": path}), mock_context)

        assert not result.success
        assert "Remote not allowed" in result.error
        assert not marker.exists()
        assert "feature" not in sh_git("branch", "--list", cwd=remote)


class TestMinimalEnvironment:
    def test_other_secrets_not_passed_to_git(self, tmp_path, monkeypatch):
        for key in ("OPENROUTER_API_KEY", "ORACLE_PASSWORD", "ZEBRA_GITLAB_TOKEN", "KAGI_API_KEY"):
            monkeypatch.setenv(key, "secret-value")
        monkeypatch.setenv("GIT_ASKPASS", "echo")

        env = GitRunner(workspace=tmp_path).env()

        assert "secret-value" not in env.values()
        assert "GIT_ASKPASS" not in env and "SSH_ASKPASS" not in env
        assert env["GIT_TERMINAL_PROMPT"] == "0"
        assert env["PATH"]

    async def test_dot_git_symlink_refused(self, workspace, remote, tmp_path, mock_context):
        path = await clone(workspace, remote, mock_context)
        outside = tmp_path / "outside-repo"
        sh_git("init", "-q", str(outside), cwd=tmp_path)
        linked = workspace / "linked"
        linked.mkdir()
        (linked / ".git").symlink_to(outside / ".git")
        assert path  # a normal clone still works

        result = await GitStatusAction().run(make_task({"repo_path": str(linked)}), mock_context)

        assert not result.success
        assert "symlink" in result.error


class TestPushNames:
    @pytest.mark.parametrize("branch", ["MAIN", "Master"])
    async def test_protected_check_ignores_case(self, branch, workspace, remote, mock_context):
        path = await clone(workspace, remote, mock_context)

        result = await GitPushAction().run(
            make_task({"repo_path": path, "branch": branch}), mock_context
        )

        assert not result.success
        assert "protected" in result.error

    async def test_invalid_branch_name_refused(self, workspace, remote, mock_context):
        path = await clone(workspace, remote, mock_context)

        result = await GitPushAction().run(
            make_task({"repo_path": path, "branch": "a..b"}), mock_context
        )

        assert not result.success
        assert "check-ref-format" in result.error


class TestLocalRemoteForms:
    """#241: without the opt-in no local form is a remote, so an armed repo is never touched."""

    @pytest.fixture
    def armed(self, workspace, remote, seed):
        """The remote armed the way the reviewer's probe did: runs a command when pushed to."""
        marker = workspace.parent / "PWNED"
        with open(remote / "config", "a") as f:
            f.write(f'[core]\n\talternateRefsCommand = "touch {marker}; :"\n')
        (remote / "objects" / "info" / "alternates").write_text(f"{seed / '.git' / 'objects'}\n")
        (workspace / "link.git").symlink_to(remote)
        return remote, marker

    async def test_armed_remote_really_fires_with_opt_in(self, armed, workspace, mock_context):
        remote, marker = armed  # the opt-in is on in the workspace fixture
        path = await clone(workspace, remote, mock_context)
        await GitBranchAction().run(
            make_task({"repo_path": path, "name": "feature", "create": True}), mock_context
        )

        await GitPushAction().run(make_task({"repo_path": path}), mock_context)

        assert marker.exists()  # so the refusals below are what keeps it from running

    @pytest.mark.parametrize(
        "form",
        [
            "{remote}",
            "file://{remote}",
            "{ws}/link.git",
            "remotes/origin.git",
            "./remotes/origin.git",
            "~/origin.git",
            "{ws}/remotes/../remotes/origin.git",
        ],
    )
    async def test_every_local_form_refused(
        self, form, armed, workspace, monkeypatch, mock_context
    ):
        remote, marker = armed
        monkeypatch.delenv("ZEBRA_GIT_ALLOW_LOCAL_REMOTES")
        url = form.format(remote=remote, ws=workspace)

        result = await GitCloneAction().run(make_task({"url": url}), mock_context)

        assert not result.success
        assert "Remote not allowed" in result.error
        assert not marker.exists()


def test_git_env_is_exactly_the_allowlist(tmp_path, monkeypatch):
    blocked = {
        "GIT_DIR": "/elsewhere",
        "GIT_EXEC_PATH": "/evil",
        "GIT_ASKPASS": "echo",
        "SSH_ASKPASS": "echo",
        "GIT_CONFIG_PARAMETERS": "'core.fsmonitor=x'",
        "SOME_RANDOM_SECRET": "x",
    }
    for key, value in {**blocked, "LC_ALL": "C.UTF-8"}.items():
        monkeypatch.setenv(key, value)

    env = GitRunner(workspace=tmp_path, token="t", token_hosts=["gitlab.com"]).env()

    count = int(env["GIT_CONFIG_COUNT"])
    own = {
        "GIT_TERMINAL_PROMPT",
        "GIT_SSH_COMMAND",
        "GIT_CONFIG_NOSYSTEM",
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_COUNT",
    } | {f"GIT_CONFIG_{kind}_{i}" for kind in ("KEY", "VALUE") for i in range(count)}
    passed_through = {k for k in env if k in _ENV_ALLOWLIST or k.startswith("LC_")}
    assert set(env) - own - passed_through == set()
    assert not set(blocked) & set(env)
    assert env["GIT_SSH_COMMAND"] == "ssh -o BatchMode=yes"
    assert env["LC_ALL"] == "C.UTF-8"
