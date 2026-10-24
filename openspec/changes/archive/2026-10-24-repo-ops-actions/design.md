## Context

The engine is fully async, so `git` runs through `asyncio.create_subprocess_exec` (never a shell).
Workflows that change code today either write files directly or go to the host builder, which has its
own sandbox and pushes itself. These actions are the light path: run Git in the Zebra container around
an `llm_agent` / `file_write` step.

## Decisions

- **One action per operation.** `reversibility_hint` is a class attribute, so a single `git` action
  with an `operation` input could only be `context_dependent`. Separate actions let the trust gate
  treat local work as reversible and `git_push` as irreversible.
- **Workspace sandbox.** `ZEBRA_GIT_WORKSPACE` (or a `workspace` property, for tests) is the root.
  `repo_path` / `dest` are resolved inside it with the filesystem `validate_path` helper. No workspace
  configured → the task fails with a configuration error.
- **Default clone destination** `<workspace>/<process id>/<repo name>` keeps reruns and parallel goals
  apart. Outputs return the absolute `path` for later steps (`{{clone.path}}` via `output_key`).
- **Remote validation.** Allowed: `https://`, `ssh://`, scp-style `user@host:path`, or a local path
  that resolves inside the workspace. Refused: anything starting with `-`, `ext::`, `file://` or
  local paths outside the workspace, plain `http://`.
- **Argument safety.** Branch, ref and path values starting with `-` are refused, and paths are passed
  after `--`.
- **Hardened environment.** `GIT_TERMINAL_PROMPT=0`, `GIT_ASKPASS=` unset-equivalent, `protocol.ext.allow=never`,
  `core.hooksPath=/dev/null` (a cloned repo cannot run hooks in Zebra).
- **Credentials.** For https remotes, if the env var named by `token_env` (default `ZEBRA_GIT_TOKEN`)
  is set, an `Authorization: Basic base64(<token_user>:<token>)` header is added via `GIT_CONFIG_COUNT`
  / `GIT_CONFIG_KEY_n` / `GIT_CONFIG_VALUE_n`. `token_user` defaults to `oauth2` (GitLab). Any
  occurrence of the token or header in stdout/stderr is replaced with `***`.
- **Commit identity** from `author_name` / `author_email` properties, else `ZEBRA_GIT_AUTHOR_NAME` /
  `ZEBRA_GIT_AUTHOR_EMAIL`, else `Zebra <zebra@localhost>`. Nothing to commit → success with
  `committed: false`, so workflows can route on it.
- **Protected branches.** `git_push` refuses `main` and `master` unless `allow_protected: true`.
- **Output size.** Diffs are truncated to `max_chars` (default 20000) with `truncated: true`, since
  outputs land in process properties.
- **Timeouts.** `timeout` property; defaults 300 s for network operations (clone, pull, push), 60 s for
  local ones. On timeout the process is killed and the task fails.

## Risks

- An agent-authored workflow could push to any branch of a repo the token can write. Mitigated by
  the irreversible hint (trust gate), the protected-branch guard and token scoping by the operator.
- Workspace grows over time (one clone per process). Acceptable for scratch; cleanup deferred.
- Container restarts wipe in-flight clones; a resumed workflow fails clearly at the next Git step.
