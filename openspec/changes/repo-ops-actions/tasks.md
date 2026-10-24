> Branch: `f64/repo-ops`. Reference `#64` in commits.

## 1. Implementation

- [x] 1.1 `zebra_tasks/vcs/base.py` — workspace resolution, remote/ref validation, repo-config allowlist, hardened env, host-scoped token header + redaction, async `GitRunner` with timeout
- [x] 1.2 `zebra_tasks/vcs/actions.py` — `git_clone`, `git_status`, `git_diff`, `git_branch`, `git_commit`, `git_pull`, `git_push`
- [x] 1.3 Register the seven entry points; `uv sync --all-packages`
- [x] 1.4 `Dockerfile`: install `git`, set `ZEBRA_GIT_WORKSPACE=/app/workspace`

## 2. Tests

- [x] 2.1 Validation: workspace escape, no workspace, remote schemes, option-like refs, edited repo config, raw-URL remotes
- [x] 2.2 Each action against a local bare remote in a tmp workspace
- [x] 2.3 Engine-level workflow: clone → branch → file_write → status → diff → commit → push
- [x] 2.4 Protected-branch guard, non-ff push, scoped token header, token redaction, timeout, metadata hints; lint + format

## 3. Docs & delivery

- [x] 3.1 `zebra-tasks/AGENTS.md`, `specs/zebra-as-is.md`
- [ ] 3.2 Zebra outcome feedback; push; green pipeline; merge; verify prod; archive; outcome review
