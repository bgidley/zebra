"""Git task actions: wrap agent work in a repository (#64).

Clone a repository into the workspace, let later steps change it (``llm_agent``, ``file_write``),
then inspect, commit and push the result. Local actions are ``always_reversible``; ``git_push`` is
``always_irreversible`` and refuses ``main``/``master`` unless ``allow_protected`` is true.

Example workflow usage:
    ```yaml
    tasks:
      clone:
        action: git_clone
        properties: {url: "https://gitlab.com/me/notes.git", output_key: repo}
      branch:
        action: git_branch
        properties: {repo_path: "{{repo.path}}", name: "zebra/{{topic}}", create: true}
      edit:
        action: llm_agent
        properties: {prompt: "Update the notes in {{repo.path}} ..."}
      commit:
        action: git_commit
        properties: {repo_path: "{{repo.path}}", message: "Update notes on {{topic}}"}
      push:
        action: git_push
        properties: {repo_path: "{{repo.path}}"}
    routings:
      - {from: commit, to: push, condition: route_name, name: committed}
    ```
"""

import logging
import os
from typing import Any, ClassVar

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.vcs.base import (
    DEFAULT_AUTHOR_EMAIL,
    DEFAULT_AUTHOR_NAME,
    LOCAL_TIMEOUT,
    NETWORK_TIMEOUT,
    GitActionError,
    bool_property,
    check_remote,
    current_branch,
    head_sha,
    in_workspace,
    make_runner,
    open_repo,
    remote_name,
    repo_name,
    resolve_workspace,
    safe_arg,
    text_property,
    timeout_property,
)

logger = logging.getLogger(__name__)

PROTECTED_BRANCHES = ("main", "master")
DEFAULT_MAX_DIFF_CHARS = 20000

_REPO_PATH = ParameterDef(
    name="repo_path",
    type="string",
    description="Repository directory inside the workspace (e.g. '{{repo.path}}' from git_clone)",
    required=True,
)
_WORKSPACE = ParameterDef(
    name="workspace",
    type="string",
    description="Workspace root; defaults to ZEBRA_GIT_WORKSPACE",
    required=False,
)
_TIMEOUT = ParameterDef(
    name="timeout", type="number", description="Seconds before Git is stopped", required=False
)
_TOKEN_ENV = ParameterDef(
    name="token_env",
    type="string",
    description="ZEBRA_GIT_TOKEN* env var holding the HTTPS token (default ZEBRA_GIT_TOKEN)",
    required=False,
)
_REMOTE = ParameterDef(
    name="remote", type="string", description="Remote name", required=False, default="origin"
)


def _output_key(default: str) -> ParameterDef:
    return ParameterDef(
        name="output_key",
        type="string",
        description="Process property for the result",
        required=False,
        default=default,
    )


class _GitAction(TaskAction):
    """Shared run(): turn GitActionError into a failed task and store the output."""

    default_output_key: ClassVar[str] = "git_result"
    reversibility_hint = "always_reversible"

    async def execute(
        self, task: TaskInstance, context: ExecutionContext
    ) -> tuple[dict[str, Any], str | None]:
        """Do the work; return ``(output, next_route)``."""
        raise NotImplementedError

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Run the Git operation, failing the task (never raising) on any error."""
        try:
            output, route = await self.execute(task, context)
        except GitActionError as e:
            return TaskResult.fail(str(e))
        key = text_property(task, context, "output_key", self.default_output_key)
        if key:
            context.set_process_property(str(key), output)
        return TaskResult(success=True, output=output, next_route=route)


class GitCloneAction(_GitAction):
    """Clone a remote repository into the workspace."""

    description = (
        "Clone a Git repository into the sandboxed workspace (default "
        "<workspace>/<process id>/<repo name>) and return its path."
    )
    default_output_key = "repo"
    inputs = [
        ParameterDef(
            name="url",
            type="string",
            description="https://, ssh:// or user@host:path remote, or a local path in workspace",
            required=True,
        ),
        ParameterDef(
            name="dest",
            type="string",
            description="Directory inside the workspace (default <process id>/<repo name>)",
            required=False,
        ),
        ParameterDef(
            name="branch", type="string", description="Branch to check out", required=False
        ),
        ParameterDef(
            name="depth", type="number", description="Shallow clone depth", required=False
        ),
        _WORKSPACE,
        _TOKEN_ENV,
        _TIMEOUT,
        _output_key("repo"),
    ]
    outputs = [
        ParameterDef(name="path", type="string", description="Absolute repository path"),
        ParameterDef(name="branch", type="string", description="Checked-out branch"),
        ParameterDef(name="head", type="string", description="HEAD commit sha"),
        ParameterDef(name="url", type="string", description="Remote cloned"),
    ]

    async def execute(self, task, context):
        workspace = resolve_workspace(task, context)
        url = check_remote(str(text_property(task, context, "url") or ""), workspace)
        dest_raw = text_property(task, context, "dest")
        dest_raw = str(dest_raw).strip() if dest_raw else f"{context.process.id}/{repo_name(url)}"
        dest = in_workspace(dest_raw, workspace)
        if dest.exists() and any(dest.iterdir()):
            raise GitActionError(f"Destination is not empty: {dest}")
        dest.parent.mkdir(parents=True, exist_ok=True)

        args = ["clone", "--no-recurse-submodules"]
        branch = text_property(task, context, "branch")
        if branch:
            args += ["--branch", safe_arg(branch, "branch")]
        depth = text_property(task, context, "depth")
        if depth:
            try:
                args += ["--depth", str(max(1, int(float(depth))))]
            except ValueError as e:
                raise GitActionError(f"Invalid depth: {depth}") from e
        args += ["--", url, str(dest)]

        runner = make_runner(task, context, workspace)
        await runner.run(args, workspace, timeout_property(task, context, NETWORK_TIMEOUT))
        return {
            "path": str(dest),
            "branch": await current_branch(runner, dest),
            "head": await head_sha(runner, dest),
            "url": runner.redact(url),
        }, None


class GitStatusAction(_GitAction):
    """Report the branch and changed files of a repository."""

    description = "Report a repository's branch and changed files; routes 'clean' or 'changed'."
    default_output_key = "git_status"
    inputs = [_REPO_PATH, _WORKSPACE, _TIMEOUT, _output_key("git_status")]
    outputs = [
        ParameterDef(name="branch", type="string", description="Current branch"),
        ParameterDef(name="clean", type="bool", description="True when nothing changed"),
        ParameterDef(
            name="files", type="list", description="Changed files: [{path, status}] (porcelain)"
        ),
        ParameterDef(name="head", type="string", description="HEAD commit sha"),
    ]

    async def execute(self, task, context):
        runner, repo = await open_repo(task, context)
        timeout = timeout_property(task, context, LOCAL_TIMEOUT)
        result = await runner.run(
            ["status", "--porcelain=v1", "--untracked-files=all"], repo, timeout
        )
        files = [
            {"status": line[:2].strip(), "path": line[3:]}
            for line in result.stdout.splitlines()
            if line.strip()
        ]
        output = {
            "branch": await current_branch(runner, repo),
            "clean": not files,
            "files": files,
            "head": await head_sha(runner, repo),
        }
        return output, "clean" if not files else "changed"


class GitDiffAction(_GitAction):
    """Return the diff of a repository's working tree."""

    description = (
        "Return the diff of a repository (working tree, staged, or against a base ref), "
        "truncated to max_chars."
    )
    default_output_key = "git_diff"
    inputs = [
        _REPO_PATH,
        ParameterDef(
            name="staged", type="bool", description="Diff the index instead", default=False
        ),
        ParameterDef(
            name="base", type="string", description="Compare the working tree to this ref"
        ),
        ParameterDef(
            name="include_untracked",
            type="bool",
            description="Show new untracked files as additions",
            default=True,
        ),
        ParameterDef(
            name="max_chars",
            type="number",
            description="Truncate the diff to this many characters",
            default=DEFAULT_MAX_DIFF_CHARS,
        ),
        _WORKSPACE,
        _TIMEOUT,
        _output_key("git_diff"),
    ]
    outputs = [
        ParameterDef(name="diff", type="string", description="Unified diff"),
        ParameterDef(name="stat", type="string", description="Diffstat summary"),
        ParameterDef(name="truncated", type="bool", description="True if the diff was cut"),
    ]

    async def execute(self, task, context):
        runner, repo = await open_repo(task, context)
        timeout = timeout_property(task, context, LOCAL_TIMEOUT)
        staged = bool_property(task, context, "staged", False)
        base = text_property(task, context, "base")

        untracked: list[str] = []
        if not staged and bool_property(task, context, "include_untracked", True):
            listed = await runner.run(["ls-files", "--others", "--exclude-standard"], repo, timeout)
            untracked = [line for line in listed.stdout.splitlines() if line]
            if untracked:
                # Intent-to-add makes new files show up in the diff without staging content.
                await runner.run(["add", "--intent-to-add", "--", *untracked], repo, timeout)

        args = ["diff", "--no-color", "--no-ext-diff"]
        if staged:
            args.append("--cached")
        if base:
            args.append(safe_arg(base, "base ref"))
        try:
            diff = (await runner.run([*args, "--"], repo, timeout)).stdout
            stat = (await runner.run([*args, "--stat", "--"], repo, timeout)).stdout
        finally:
            if untracked:
                await runner.run(["reset", "--quiet", "--", *untracked], repo, timeout)

        try:
            max_chars = int(
                float(text_property(task, context, "max_chars", DEFAULT_MAX_DIFF_CHARS))
            )
        except (TypeError, ValueError):
            max_chars = DEFAULT_MAX_DIFF_CHARS
        truncated = len(diff) > max_chars
        return {
            "diff": diff[:max_chars],
            "stat": stat.strip(),
            "truncated": truncated,
        }, None


class GitBranchAction(_GitAction):
    """Check out a branch, optionally creating it."""

    description = "Check out a branch in a repository, creating it from start_point if asked."
    default_output_key = "git_branch"
    inputs = [
        _REPO_PATH,
        ParameterDef(name="name", type="string", description="Branch name", required=True),
        ParameterDef(
            name="create", type="bool", description="Create the branch first", default=False
        ),
        ParameterDef(
            name="start_point",
            type="string",
            description="Ref to create the branch from (default HEAD)",
        ),
        _WORKSPACE,
        _TIMEOUT,
        _output_key("git_branch"),
    ]
    outputs = [
        ParameterDef(name="branch", type="string", description="Checked-out branch"),
        ParameterDef(name="created", type="bool", description="True if the branch was created"),
        ParameterDef(name="head", type="string", description="HEAD commit sha"),
    ]

    async def execute(self, task, context):
        runner, repo = await open_repo(task, context)
        timeout = timeout_property(task, context, LOCAL_TIMEOUT)
        name = safe_arg(text_property(task, context, "name") or "", "branch name")
        await runner.run(["check-ref-format", "--branch", name], repo, timeout)
        create = bool_property(task, context, "create", False)
        args = ["switch"]
        if create:
            args += ["--create", name]
            start = text_property(task, context, "start_point")
            if start:
                args.append(safe_arg(start, "start_point"))
        else:
            args.append(name)
        await runner.run(args, repo, timeout)
        return {
            "branch": await current_branch(runner, repo),
            "created": create,
            "head": await head_sha(runner, repo),
        }, None


class GitCommitAction(_GitAction):
    """Stage changes and commit them."""

    description = (
        "Stage changes (all, or the given paths) and commit them; routes 'committed' or "
        "'nothing_to_commit'."
    )
    default_output_key = "git_commit"
    inputs = [
        _REPO_PATH,
        ParameterDef(name="message", type="string", description="Commit message", required=True),
        ParameterDef(
            name="paths", type="list", description="Paths to stage (default: all changes)"
        ),
        ParameterDef(
            name="author_name",
            type="string",
            description="Author name (default ZEBRA_GIT_AUTHOR_NAME, else 'Zebra')",
        ),
        ParameterDef(
            name="author_email",
            type="string",
            description="Author email (default ZEBRA_GIT_AUTHOR_EMAIL, else zebra@localhost)",
        ),
        _WORKSPACE,
        _TIMEOUT,
        _output_key("git_commit"),
    ]
    outputs = [
        ParameterDef(name="committed", type="bool", description="False when nothing changed"),
        ParameterDef(name="sha", type="string", description="New commit sha (or HEAD)"),
        ParameterDef(name="branch", type="string", description="Branch committed to"),
        ParameterDef(name="files", type="list", description="Files in the commit"),
    ]

    async def execute(self, task, context):
        runner, repo = await open_repo(task, context)
        timeout = timeout_property(task, context, LOCAL_TIMEOUT)
        message = str(text_property(task, context, "message") or "").strip()
        if not message:
            raise GitActionError("No commit message provided")

        paths = task.properties.get("paths")
        if isinstance(paths, str):
            paths = [paths]
        if paths:
            resolved = [
                safe_arg(context.resolve_template(str(p)), "path") for p in paths if str(p).strip()
            ]
            for p in resolved:
                in_workspace(str(repo / p), runner.workspace)
            await runner.run(["add", "--all", "--", *resolved], repo, timeout)
        else:
            await runner.run(["add", "--all"], repo, timeout)

        staged = await runner.run(["diff", "--cached", "--name-only"], repo, timeout)
        files = [line for line in staged.stdout.splitlines() if line]
        branch = await current_branch(runner, repo)
        if not files:
            return {
                "committed": False,
                "sha": await head_sha(runner, repo),
                "branch": branch,
                "files": [],
            }, "nothing_to_commit"

        name = text_property(task, context, "author_name") or os.environ.get(
            "ZEBRA_GIT_AUTHOR_NAME", DEFAULT_AUTHOR_NAME
        )
        email = text_property(task, context, "author_email") or os.environ.get(
            "ZEBRA_GIT_AUTHOR_EMAIL", DEFAULT_AUTHOR_EMAIL
        )
        identity = ["-c", f"user.name={name}", "-c", f"user.email={email}"]
        await runner.run(
            [*identity, "commit", "--no-verify", "--file", "-", "--quiet"],
            repo,
            timeout,
            stdin=message,
        )
        return {
            "committed": True,
            "sha": await head_sha(runner, repo),
            "branch": branch,
            "files": files,
        }, "committed"


class GitPullAction(_GitAction):
    """Fast-forward the current branch from its remote."""

    description = "Pull the current branch from a remote, fast-forward only."
    default_output_key = "git_pull"
    inputs = [
        _REPO_PATH,
        _REMOTE,
        ParameterDef(name="branch", type="string", description="Remote branch to pull"),
        _WORKSPACE,
        _TOKEN_ENV,
        _TIMEOUT,
        _output_key("git_pull"),
    ]
    outputs = [
        ParameterDef(name="branch", type="string", description="Current branch"),
        ParameterDef(name="before", type="string", description="HEAD before the pull"),
        ParameterDef(name="head", type="string", description="HEAD after the pull"),
        ParameterDef(name="updated", type="bool", description="True if HEAD moved"),
    ]

    async def execute(self, task, context):
        runner, repo = await open_repo(task, context)
        remote = await remote_name(
            runner, repo, text_property(task, context, "remote", "origin") or "origin"
        )
        args = ["pull", "--ff-only", "--no-rebase", remote]
        branch = text_property(task, context, "branch")
        if branch:
            args.append(safe_arg(branch, "branch"))
        before = await head_sha(runner, repo)
        await runner.run(args, repo, timeout_property(task, context, NETWORK_TIMEOUT))
        head = await head_sha(runner, repo)
        return {
            "branch": await current_branch(runner, repo),
            "before": before,
            "head": head,
            "updated": head != before,
        }, None


class GitPushAction(_GitAction):
    """Push a branch to a remote. Irreversible; refuses protected branches by default."""

    description = (
        "Push a branch to a remote (never forced). Refuses main/master unless allow_protected "
        "is true."
    )
    default_output_key = "git_push"
    reversibility_hint = "always_irreversible"
    inputs = [
        _REPO_PATH,
        _REMOTE,
        ParameterDef(
            name="branch", type="string", description="Branch to push (default: current branch)"
        ),
        ParameterDef(
            name="allow_protected",
            type="bool",
            description="Allow pushing main/master",
            default=False,
        ),
        _WORKSPACE,
        _TOKEN_ENV,
        _TIMEOUT,
        _output_key("git_push"),
    ]
    outputs = [
        ParameterDef(name="remote", type="string", description="Remote pushed to"),
        ParameterDef(name="branch", type="string", description="Branch pushed"),
        ParameterDef(name="head", type="string", description="Commit pushed"),
    ]

    async def execute(self, task, context):
        runner, repo = await open_repo(task, context)
        remote = await remote_name(
            runner, repo, text_property(task, context, "remote", "origin") or "origin"
        )
        branch = text_property(task, context, "branch") or await current_branch(runner, repo)
        branch = safe_arg(branch, "branch")
        await runner.run(["check-ref-format", "--branch", branch], repo)
        if branch.lower() in PROTECTED_BRANCHES and not bool_property(
            task, context, "allow_protected", False
        ):
            raise GitActionError(
                f"Refusing to push protected branch '{branch}'; set allow_protected: true"
            )
        await runner.run(
            ["push", "--no-verify", remote, f"refs/heads/{branch}:refs/heads/{branch}"],
            repo,
            timeout_property(task, context, NETWORK_TIMEOUT),
        )
        logger.info("Pushed %s to %s from %s", branch, remote, repo)
        return {
            "remote": remote,
            "branch": branch,
            "head": await head_sha(runner, repo),
        }, None
