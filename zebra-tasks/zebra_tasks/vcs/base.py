"""Shared helpers for the Git task actions (#64).

Every repository lives under one workspace directory (the ``workspace`` property, else
``ZEBRA_GIT_WORKSPACE``). Git runs as an async subprocess, never through a shell, with a hardened
environment: no prompts, no repository hooks and no ``ext::`` transport. HTTPS credentials are
passed through ``GIT_CONFIG_*`` environment variables, so they never appear in argv, and are
redacted from anything the actions return.
"""

import asyncio
import base64
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from zebra.core.models import TaskInstance
from zebra.tasks.base import ExecutionContext

from zebra_tasks.filesystem.base import FileSystemConfig, FileSystemError, validate_path

WORKSPACE_ENV = "ZEBRA_GIT_WORKSPACE"
DEFAULT_TOKEN_ENV = "ZEBRA_GIT_TOKEN"
DEFAULT_TOKEN_USER = "oauth2"
TOKEN_HOSTS_ENV = "ZEBRA_GIT_TOKEN_HOSTS"
DEFAULT_TOKEN_HOSTS = "gitlab.com"
DEFAULT_AUTHOR_NAME = "Zebra"
DEFAULT_AUTHOR_EMAIL = "zebra@localhost"
LOCAL_TIMEOUT = 60
NETWORK_TIMEOUT = 300
REDACTED = "***"

_SCP_REMOTE = re.compile(r"^[\w.-]+@[\w.-]+:.+$")
# Repository config keys a clone/branch/commit can legitimately produce. Anything else (fsmonitor,
# sshCommand, filter drivers, insteadOf, includes, aliases, ...) could run commands or redirect Git.
_ALLOWED_CONFIG = re.compile(
    r"^(core\.(repositoryformatversion|filemode|bare|logallrefupdates|ignorecase"
    r"|precomposeunicode|symlinks)"
    r"|remote\..+\.(url|pushurl|fetch|tagopt)"
    r"|branch\..+\.(remote|merge)"
    r"|extensions\.objectformat)$"
)
_REMOTE_URL_KEY = re.compile(r"^remote\..+\.(url|pushurl)$")
# Environment passed to git; everything else (API keys, DB credentials, tokens) is dropped.
_ENV_ALLOWLIST = frozenset(
    {
        "PATH",
        "HOME",
        "LANG",
        "LANGUAGE",
        "TZ",
        "TMPDIR",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "http_proxy",
        "https_proxy",
        "no_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
    }
)
# Local-path remotes are only for tests and development: on local transport git runs the other
# repository's upload-pack/receive-pack without our hardening, so that repository's own config and
# hooks could run commands (#241).
ALLOW_LOCAL_REMOTES_ENV = "ZEBRA_GIT_ALLOW_LOCAL_REMOTES"


class GitActionError(Exception):
    """A Git action cannot run: bad input, refused by the sandbox, or Git failed."""


@dataclass
class GitResult:
    """Outcome of one ``git`` invocation, with secrets already redacted."""

    returncode: int
    stdout: str
    stderr: str


@dataclass
class GitRunner:
    """Runs ``git`` inside the workspace with a hardened environment.

    Attributes:
        workspace: Resolved workspace root; every path must stay inside it.
        token: HTTPS token sent as a Basic auth header, or None.
        token_user: User name paired with the token (``oauth2`` for GitLab).
        secrets: Strings scrubbed from every output.
    """

    workspace: Path
    token: str | None = None
    token_user: str = DEFAULT_TOKEN_USER
    token_hosts: list[str] = field(default_factory=list)
    secrets: list[str] = field(default_factory=list)

    def env(self) -> dict[str, str]:
        """Return the subprocess environment for ``git``.

        Only an allowlist of the process environment is passed on, so nothing git starts sees
        Zebra's other secrets (API keys, database credentials). There is no askpass helper and
        prompts are off, so an auth challenge fails at once.
        """
        env = {
            key: value
            for key, value in os.environ.items()
            if key in _ENV_ALLOWLIST or key.startswith("LC_")
        }
        env.update(
            {
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_SSH_COMMAND": "ssh -o BatchMode=yes",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
            }
        )
        config = [
            ("protocol.ext.allow", "never"),
            ("core.hooksPath", os.devnull),
            ("credential.helper", ""),
        ]
        if self.token:
            # Scoped per host, so the token is only ever sent to the hosts it was issued for.
            basic = base64.b64encode(f"{self.token_user}:{self.token}".encode()).decode()
            for host in self.token_hosts:
                config.append(
                    (f"http.https://{host}/.extraHeader", f"Authorization: Basic {basic}")
                )
            self.secrets.extend([self.token, basic])
        env["GIT_CONFIG_COUNT"] = str(len(config))
        for i, (key, value) in enumerate(config):
            env[f"GIT_CONFIG_KEY_{i}"] = key
            env[f"GIT_CONFIG_VALUE_{i}"] = value
        return env

    def redact(self, text: str) -> str:
        """Replace every known secret in *text* with ``***``."""
        for secret in self.secrets:
            if secret:
                text = text.replace(secret, REDACTED)
        return text

    async def run(
        self,
        args: list[str],
        cwd: Path,
        timeout: float = LOCAL_TIMEOUT,
        check: bool = True,
        stdin: str | None = None,
    ) -> GitResult:
        """Run ``git <args>`` in *cwd* and return its redacted output.

        Raises:
            GitActionError: On timeout, a missing ``git`` binary, or (with *check*) a non-zero exit.
        """
        env = self.env()
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                *args,
                cwd=str(cwd),
                env=env,
                stdin=asyncio.subprocess.DEVNULL if stdin is None else asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as e:
            raise GitActionError("git is not installed on this host") from e
        data = stdin.encode() if stdin is not None else None
        try:
            out, err = await asyncio.wait_for(proc.communicate(data), timeout=timeout)
        except TimeoutError as e:
            try:
                proc.kill()
            except ProcessLookupError:  # it exited just as the timeout fired
                pass
            await proc.wait()
            raise GitActionError(f"git {args[0]} timed out after {timeout:g}s") from e
        result = GitResult(
            returncode=proc.returncode or 0,
            stdout=self.redact(out.decode(errors="replace")),
            stderr=self.redact(err.decode(errors="replace")),
        )
        if check and result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise GitActionError(f"git {args[0]} failed: {detail}")
        return result


def text_property(task: TaskInstance, context: ExecutionContext, key: str, default=None):
    """Return a task property with ``{{templates}}`` resolved; non-strings pass through."""
    value = task.properties.get(key, default)
    if isinstance(value, str) and "{{" in value:
        value = context.resolve_template(value)
    return value


def bool_property(task: TaskInstance, context: ExecutionContext, key: str, default: bool) -> bool:
    """Return a boolean task property, accepting templated ``"true"``/``"false"`` strings."""
    value = text_property(task, context, key, default)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes")
    return bool(value)


def resolve_workspace(task: TaskInstance, context: ExecutionContext) -> Path:
    """Return the workspace root, creating it if needed.

    ``ZEBRA_GIT_WORKSPACE`` is the root. A ``workspace`` property may narrow it to a directory
    inside that root; it is only used on its own when the env var is unset (development, tests).

    Raises:
        GitActionError: If no workspace is configured, or the property escapes the root.
    """
    env_root = os.environ.get(WORKSPACE_ENV)
    raw = text_property(task, context, "workspace")
    if env_root and raw:
        workspace = in_workspace(str(raw).strip(), Path(env_root).resolve())
    elif env_root or raw:
        workspace = Path(str(env_root or raw)).resolve()
    else:
        raise GitActionError(
            f"No Git workspace configured: set {WORKSPACE_ENV} or the 'workspace' property"
        )
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def in_workspace(path: str, workspace: Path) -> Path:
    """Resolve *path* (relative to, or absolute inside, the workspace) and keep it inside.

    Raises:
        GitActionError: If the path escapes the workspace.
    """
    config = FileSystemConfig(base_directory=workspace, allow_absolute=True, follow_symlinks=True)
    try:
        return validate_path(path, config)
    except FileSystemError as e:
        raise GitActionError(f"Security error: {e}") from e


def safe_arg(value: str, what: str) -> str:
    """Refuse values Git could read as an option.

    Raises:
        GitActionError: If *value* is empty or starts with ``-``.
    """
    value = str(value).strip()
    if not value:
        raise GitActionError(f"No {what} provided")
    if value.startswith("-"):
        raise GitActionError(f"Refusing {what} that looks like an option: {value!r}")
    return value


def check_remote(url: str, workspace: Path) -> str:
    """Return *url* if it is an allowed remote.

    Allowed: ``https://``, ``ssh://`` and scp-style ``user@host:path``. A local path inside the
    workspace is allowed only when ``ZEBRA_GIT_ALLOW_LOCAL_REMOTES=1`` (tests, development; #241).
    Everything else (``ext::``, ``file://``, ``http://``, outside paths) is refused.

    Raises:
        GitActionError: If the remote is not allowed.
    """
    url = safe_arg(url, "remote URL")
    lowered = url.lower()
    if lowered.startswith(("https://", "ssh://")) or _SCP_REMOTE.match(url):
        return url
    if "::" in url or "://" in url:
        raise GitActionError(f"Remote not allowed (use https:// or ssh://): {url}")
    if os.environ.get(ALLOW_LOCAL_REMOTES_ENV) != "1":
        raise GitActionError(f"Remote not allowed (use https:// or ssh://): {url}")
    path = Path(url)
    if not path.is_absolute():
        raise GitActionError(f"Remote not allowed: {url}")
    in_workspace(url, workspace)
    return url


def repo_name(url: str) -> str:
    """Return the repository name from a remote URL (``group/proj.git`` → ``proj``)."""
    name = re.split(r"[/:]", url.rstrip("/"))[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name or "repo"


def make_runner(task: TaskInstance, context: ExecutionContext, workspace: Path) -> GitRunner:
    """Build a runner with the token named by ``token_env`` (default ``ZEBRA_GIT_TOKEN``).

    ``token_env`` must name a ``ZEBRA_GIT_TOKEN*`` variable, so a workflow cannot send any other
    secret as a credential. The token is only offered to hosts in ``ZEBRA_GIT_TOKEN_HOSTS``.

    Raises:
        GitActionError: If ``token_env`` names some other variable.
    """
    token_env = str(task.properties.get("token_env") or DEFAULT_TOKEN_ENV).strip()
    if not token_env.startswith(DEFAULT_TOKEN_ENV):
        raise GitActionError(f"token_env must name a {DEFAULT_TOKEN_ENV}* variable: {token_env}")
    hosts = os.environ.get(TOKEN_HOSTS_ENV, DEFAULT_TOKEN_HOSTS)
    return GitRunner(
        workspace=workspace,
        token=os.environ.get(token_env) or None,
        token_user=str(task.properties.get("token_user") or DEFAULT_TOKEN_USER),
        token_hosts=[h.strip().lower() for h in hosts.split(",") if h.strip()],
    )


async def open_repo(task: TaskInstance, context: ExecutionContext) -> tuple[GitRunner, Path]:
    """Resolve ``repo_path`` inside the workspace and check it is a Git repository.

    Raises:
        GitActionError: If the path is missing, outside the workspace or not a repository.
    """
    workspace = resolve_workspace(task, context)
    raw = text_property(task, context, "repo_path")
    if not raw:
        raise GitActionError("No repo_path provided")
    path = in_workspace(str(raw).strip(), workspace)
    dot_git = path / ".git"
    if dot_git.is_symlink():
        raise GitActionError(f"Refusing repository whose .git is a symlink: {path}")
    if not dot_git.is_dir():
        raise GitActionError(f"Not a Git repository: {path}")
    runner = make_runner(task, context, workspace)
    await check_repo_config(runner, path)
    return runner, path


async def check_repo_config(runner: GitRunner, repo: Path) -> None:
    """Refuse a repository whose local config could run commands or reach other remotes.

    Steps between Git actions (an ``llm_agent`` with file tools, ``file_write``) can edit
    ``.git/config``. Keys such as ``core.fsmonitor``, ``filter.*`` or ``url.*.insteadOf`` would let
    them run commands or redirect a push, so only plain clone/branch settings are allowed, and every
    remote URL must pass :func:`check_remote`.

    Raises:
        GitActionError: If the config has a key outside the allowlist or a disallowed remote URL.
    """
    result = await runner.run(["config", "--local", "--list", "--null"], repo)
    for entry in result.stdout.split("\0"):
        if not entry:
            continue
        key, _, value = entry.partition("\n")
        if not _ALLOWED_CONFIG.match(key):
            raise GitActionError(f"Refusing repository with unsupported config key '{key}'")
        if _REMOTE_URL_KEY.match(key):
            check_remote(value, runner.workspace)


async def remote_name(runner: GitRunner, repo: Path, name: str) -> str:
    """Return *name* if it is a configured remote of *repo* (never a raw URL).

    Raises:
        GitActionError: If the remote is not configured.
    """
    name = safe_arg(name, "remote")
    result = await runner.run(["remote"], repo)
    if name not in result.stdout.split():
        raise GitActionError(f"Unknown remote '{name}' (configure it by cloning)")
    return name


async def current_branch(runner: GitRunner, repo: Path) -> str:
    """Return the checked-out branch name (empty when HEAD is detached)."""
    result = await runner.run(["symbolic-ref", "--quiet", "--short", "HEAD"], repo, check=False)
    return result.stdout.strip()


async def head_sha(runner: GitRunner, repo: Path) -> str:
    """Return the HEAD commit sha (empty for a repository with no commits)."""
    result = await runner.run(["rev-parse", "--verify", "--quiet", "HEAD"], repo, check=False)
    return result.stdout.strip()


def timeout_property(task: TaskInstance, context: ExecutionContext, default: int) -> float:
    """Return the ``timeout`` property in seconds, falling back to *default*."""
    raw = text_property(task, context, "timeout", default)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return float(default)
    return value if value > 0 else float(default)
