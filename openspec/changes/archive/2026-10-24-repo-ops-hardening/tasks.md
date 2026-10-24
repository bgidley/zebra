> Branch: `f241/repo-hardening`. Reference `#241` in commits.

## 1. Implementation

- [x] 1.1 `check_remote`: local paths only with `ZEBRA_GIT_ALLOW_LOCAL_REMOTES=1`
- [x] 1.2 `GitRunner.env`: environment allowlist, no askpass, batch-mode ssh
- [x] 1.3 `open_repo`: refuse `.git` symlink; `git_push`: `check-ref-format`, case-insensitive protected check

## 2. Tests

- [x] 2.1 Armed local remote (alternateRefsCommand + pre-receive) refused as clone source and push target
- [x] 2.2 Secrets not in the Git environment; `.git` symlink; push names

## 3. Docs & delivery

- [x] 3.1 `zebra-tasks/AGENTS.md`, `specs/zebra-as-is.md`
- [x] 3.2 Zebra outcome feedback; pipeline; merge; prod check; archive; outcome review
