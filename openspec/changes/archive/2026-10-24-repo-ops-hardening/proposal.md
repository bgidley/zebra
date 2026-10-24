## Why

The #64 outcome review found that a remote which is a local path in the workspace bypasses the Git
actions' hardening: on local transport git runs the other repository's `upload-pack` /
`receive-pack` without our `GIT_CONFIG_*` settings, so that repository's own config
(`core.alternateRefsCommand`) or hooks run commands, and those commands saw the token header and every
other secret in the environment. Closes #241.

## What Changes

- Local-path remotes are refused unless `ZEBRA_GIT_ALLOW_LOCAL_REMOTES=1` (tests and development only;
  never set in prod). This also applies to remote URLs found in a repository's config.
- Git runs with a minimal allowlisted environment (`PATH`, `HOME`, locale, `TZ`, `TMPDIR`, CA and
  proxy variables) plus its own hardening; API keys, database credentials and other tokens are dropped.
- No askpass helper (`GIT_ASKPASS` dropped, `GIT_SSH_COMMAND="ssh -o BatchMode=yes"`), so an auth
  challenge fails at once.
- A `.git` that is a symlink is refused.
- `git_push` checks the branch with `check-ref-format`, and the protected-branch check ignores case.

## Capabilities

### New Capabilities
<!-- None -->

### Modified Capabilities
- `repo-ops-actions`: local remotes opt-in, minimal environment, `.git` symlink and push-name checks.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | A local repository cannot be used to run commands through the Git actions in prod | Regression tests: a bare repo armed with `core.alternateRefsCommand` (positive control: with the opt-in, pushing to it runs the command) and a `pre-receive` hook is refused without the opt-in as a clone source in every local form (absolute, `file://`, relative, `./`, `~`, `..`, symlink into the workspace) and as a push target via `remote.origin.url`, and its sentinel file is never created; prod has no `ZEBRA_GIT_ALLOW_LOCAL_REMOTES` |
| O2 | Nothing Git starts can see Zebra's other secrets | Tests: the Git environment's keys are exactly the stated allowlist plus Git's own settings; `OPENROUTER_API_KEY`, `ORACLE_PASSWORD`, `ZEBRA_GITLAB_TOKEN`, `KAGI_API_KEY`, an arbitrary secret, `GIT_DIR`, `GIT_EXEC_PATH`, `GIT_CONFIG_PARAMETERS` and askpass variables from the parent never appear |
| O3 | Remaining repository tricks are refused | Tests: `.git` symlink refused; `git_push` refuses `a..b`, `MAIN` and `Master` |
| O4 | Normal https use in prod still works | After deploy, inside `zebra-web`: the actions clone a public https repo, branch and commit; a local-path clone is refused |

## Non-goals

- Making local remotes safe (they stay a development convenience).
- A host allow-list for https/ssh remotes.

## Impact

- `zebra_tasks/vcs/base.py`, `actions.py`, tests; docs in `zebra-tasks/AGENTS.md` and `specs/zebra-as-is.md`.
