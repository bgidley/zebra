> Branch: `f282/contribute-diff-scan`. Commit with `Part of #282` (slice A of five; do not close #282).

## 1. Scanner

- [x] 1.1 `zebra_tasks/contribute/diff_scan.py`: diff parser (hunk counts, added lines, binaries, deletions, renames, preamble text)
- [x] 1.2 Rules: reuse `rule_findings` and `confidential_rule_findings` (minus `url` / `credential` / `internal_host`, plus code-aware `host_findings`), secret rules, entropy, blocked and sensitive paths, noreply allowlist
- [x] 1.3 `scan_diff` (size cap, one low-tier LLM call, fail closed, masked located findings, noreply author email, diff sha256) and `ContributeDiffScanAction` (`always_reversible`)
- [x] 1.4 Entry point `contribute_diff_scan`; `uv sync --all-packages`

## 2. Tests

- [x] 2.1 One known-bad diff per rule; added-only (removed, context, deleted file); messages, PR body, path
- [x] 2.2 Fail closed: empty, malformed, size cap, no LLM, failed call, empty / verdict-less reply, LLM positive
- [x] 2.3 A real repo diff passes; sensitive files flagged; noreply email; action stores its output

## 3. Docs

- [x] 3.1 `specs/zebra-as-is.md`, `zebra-tasks/AGENTS.md`
