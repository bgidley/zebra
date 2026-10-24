## Context

Git hands the other repository's `upload-pack` / `receive-pack` a sanitised environment on local
transport: `GIT_CONFIG_COUNT` and `GIT_CONFIG_PARAMETERS` are dropped (git's `local_repo_env`), so
command-line config such as `core.hooksPath=/dev/null` never reaches it. That repository's config and
hooks then apply. The `GIT_CONFIG_VALUE_n` variables (carrying the auth header) are not dropped.

## Decisions

- **Refuse local remotes by default** rather than try to harden the remote side. Checking another
  repository's config and hooks before every transfer is fragile (alternates, includes, new keys in
  future git versions); there is no production need for local remotes.
- **Opt-in env var for tests** (`ZEBRA_GIT_ALLOW_LOCAL_REMOTES=1`), checked in `check_remote`, which
  also guards remote URLs in a repository's config, so `remote.origin.url` cannot be pointed at a
  local path either.
- **Environment allowlist** instead of a deny list: anything git starts gets only what git needs.
- **No askpass**: `GIT_TERMINAL_PROMPT=0` with no askpass makes git fail on a 401 instead of sending
  the prompt text as credentials.

## Risks

- A developer who sets the opt-in runs the old risk locally; documented as development-only.
