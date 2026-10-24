## Why

Workflows can already change files (`file_write`, `llm_agent` with tools) and hand whole builds to the
host builder (`claude_code_build`), but they cannot put a repository around that work: clone it,
branch, see what an agent changed, commit and push. Without that, an agent's edits stay in a scratch
directory nobody can review. Closes #64.

## What Changes

- Seven task actions in a new `zebra_tasks/vcs/` package: `git_clone`, `git_status`, `git_diff`,
  `git_branch`, `git_commit`, `git_pull`, `git_push`. They run the `git` binary as an async
  subprocess (no shell), with a timeout.
- Every repository lives under one workspace directory, `ZEBRA_GIT_WORKSPACE`. Paths outside it are
  refused. A clone defaults to `<workspace>/<process id>/<repo name>`, so reruns never collide.
- Remotes must be `https://`, `ssh://` or `user@host:path`, or a local path inside the workspace.
  Option-looking values (leading `-`) and `ext::` transports are refused.
- HTTPS credentials come from an env var named by `token_env` (default `ZEBRA_GIT_TOKEN`). The token
  is passed through `GIT_CONFIG_*` env vars, never in argv, and redacted from outputs and errors.
- `git_push` declares `reversibility_hint = "always_irreversible"` and refuses `main`/`master`
  unless `allow_protected: true`. There is no force push. The other six are `always_reversible`
  (local only; `git_pull` is fast-forward only).
- Prod image installs `git` and sets `ZEBRA_GIT_WORKSPACE=/app/workspace`.

## Capabilities

### New Capabilities
- `repo-ops-actions`: Git task actions for wrapping agent work in a repository.

### Modified Capabilities
<!-- None -->

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | A workflow can clone a repo, let a step change it, commit, and push a branch | Engine-level test runs clone → `file_write` → status/diff → commit → push against a local bare remote; the remote's branch has the commit with the given message and the configured author. Nothing to commit routes `nothing_to_commit`; a non-empty clone destination and a rejected (non-fast-forward) push fail the task cleanly |
| O2 | Pushing is treated as irreversible and cannot hit protected branches by accident | `git_push` metadata is `always_irreversible`; the destination ref is always `refs/heads/<branch>` of the checked branch, and `main`/`master` fail without `allow_protected`; no force option exists |
| O3 | The actions stay inside their sandbox and keep credentials to their scoped host | Leak-vector test matrix: paths outside the workspace, `-`-prefixed refs, `ext::`/`file://`/out-of-workspace remotes, raw-URL remotes on push, and a `.git/config` edited to add `core.fsmonitor`/`filter.*`/`url.*.insteadOf` are all refused; `token_env` other than `ZEBRA_GIT_TOKEN*` refused; positive test: the auth header is in the Git env scoped to `ZEBRA_GIT_TOKEN_HOSTS` only, never in argv, and the token is redacted from outputs and errors |
| O4 | Prod can run Git workflows (prerequisite) | After deploy, inside `zebra-web`: `git --version` works, `ZEBRA_GIT_WORKSPACE` is set and writable, a clone → commit → push to a throwaway bare remote in the workspace succeeds through the actions, and `git ls-remote` of a public https repo works (DNS/CA) |
| O5 | Workflow authors (and the workflow creator) can find and use the actions (prerequisite) | Seven entry points load in the registry; `zebra-tasks/AGENTS.md` and `specs/zebra-as-is.md` describe them with the example workflow used by the O1 test |

## Non-goals

- Force push, rebase, merge, tags, submodules, LFS.
- Opening merge/pull requests (a later HTTP/GitLab integration, #62/#37).
- A host allow-list for remotes; trust and ethics gates apply at the workflow level.
- Persisting the workspace across deploys; it is scratch space.

## Impact

- New package `zebra-tasks/zebra_tasks/vcs/`, seven entry points, tests in `zebra-tasks/tests/vcs/`.
- No new Python dependencies. `Dockerfile` runtime stage gains the `git` package.
