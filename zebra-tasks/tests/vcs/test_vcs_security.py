"""Leak-vector matrix for the Git task actions (#64): sandbox, remotes, config, credentials."""

import pytest

from vcs.helpers import make_task
from zebra_tasks.vcs.actions import (
    GitCloneAction,
    GitCommitAction,
    GitPullAction,
    GitPushAction,
    GitStatusAction,
)
from zebra_tasks.vcs.base import GitActionError, GitRunner, check_remote


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
