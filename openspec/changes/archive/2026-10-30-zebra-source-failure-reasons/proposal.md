## Why

Zebra's dream cycle reported that `zebra_source` failures do not let a caller tell access policy
from absence: a protected file, a path that is in the repository but not deployed, and a file that
does not exist all come back as plain failure text. The messages already differ in wording, but
nothing machine-readable says which case it is, and an `OSError` while reading escapes as an
exception instead of a task failure. Closes #258.

## What Changes

- Every `zebra_source` failure starts with a `[reason]` tag, one of `protected`, `not_deployed`,
  `missing`, `invalid`, `error` (`REASONS`). The message after the tag and the closing
  list/search hint are unchanged.
- `SourceAccessError` requires a reason; `missing_path_message()` becomes `missing_path_error()`,
  which picks `missing` or `not_deployed`.
- An `OSError` while reading fails the task with `[error]` instead of raising.

The tag goes in the error text because a failed tool workflow reaches `llm_agent` only as text
(`TaskResult.fail` carries no output).

## Capabilities

### New Capabilities
- `zebra-source-access`: failure reasons for Zebra's read-only source access.

### Modified Capabilities
<!-- None -->

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | Every `zebra_source` failure starts with exactly one of five reason tags and still ends with the recovery hint | Parametrized test over every failure path (`test_every_failure_starts_with_its_reason`): each error fully matches `^\[(protected\|not_deployed\|missing\|invalid\|error)\] .+ <hint>$` |
| O2 | A caller can tell protected, not-deployed and missing paths apart | Tests: `.env`, a hidden path that does not exist, `../x`, a symlink out and an off-allowlist entry → `[protected]`; `specs/…` in a tree without `specs/` → `[not_deployed]`; a missing file → `[missing]`. Precedence: protected before existence, then not_deployed / missing. In prod (`zebra-web`): `.env` → `[protected]`, `zebra-tasks/nope.py` → `[missing]` |
| O3 | An unreadable file fails the task with `[error]` instead of raising | Test: `read_text` raising `PermissionError` gives `[error] Could not read the source: …` ending with the hint |
| O4 | Successful reads, lists and searches are unchanged | The existing `zebra_source` and outcome-review workflow tests pass with only the refusal-prefix assertions updated |

## Non-goals

- A structured `reason` output field (a failed task has no output; the tag is the contract).
- Changing which paths are readable, or the #255 change to listing a file path.
