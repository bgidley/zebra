> Branch: `f258/source-reasons`. Reference `#258` in commits.

## 1. Implementation

- [x] 1.1 `SourceAccessError(message, reason)`, `REASONS`; reason at every raise site
- [x] 1.2 `missing_path_error()` picks `missing` / `not_deployed`
- [x] 1.3 `run()`: `[reason] ` prefix; `OSError` → `[error]`

## 2. Tests

- [x] 2.1 Refusal-prefix tests updated; parametrized reason test over every failure path
- [x] 2.2 `PermissionError` while reading → `[error]`, not a crash

## 3. Docs & delivery

- [x] 3.1 `zebra-tasks/AGENTS.md`, `specs/zebra-as-is.md`
- [x] 3.2 Outcomes posted on #258 and Zebra feedback (adopted: full-message regex, hidden-but-absent
  case, O4 restated; declined: a repo-only manifest — the allowlist is the source of truth)
- [ ] 3.3 GitLab CI green, merged, deployed; prod check of O2
- [ ] 3.4 Archive this change; outcome review
