## Why

The #282-A outcome review ruled three gaps in `contribute_diff_scan`: lock-file lines skip the
personal-data and confidential rules (#301), only the LLM payload is size-capped and a bare
diff file header counts as a file (#302), and "writes nothing but its output" ignores the LLM
client's cost bookkeeping (#303). Refs #282, #275.

## What Changes

- Lock-file added lines also get the personal-data rules and the confidential patterns (still no
  LLM, no host rule); URLs, hashes, `version = "..."` values and the `ip_address` kind are tuned out
  for lock lines after measuring this repo's `uv.lock`.
- A hard `MAX_DIFF_CHARS` (2,000,000) cap on the raw diff fails closed before parsing.
- A file entry with no hunk, binary patch, mode, rename or copy line is malformed (fails closed);
  mode-only changes, empty new files, empty deletions and pure renames still parse.
- The spec and code state the real write guarantee: the `output_key` property plus the LLM client's
  bookkeeping keys (`LLM_BOOKKEEPING_KEYS`); a test names them.
- `scan_diff_text` keeps its interface.

## Capabilities

### Modified Capabilities
- `contribute-diff-scan`: lock-file rules, raw size cap, malformed file entries, write guarantee.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | An email, phone, postcode or confidential pattern added in a lock file rejects; real `uv.lock` content stays clean | Per-rule lock-file tests plus a test scanning this repo's `uv.lock` |
| O2 | A raw diff over `MAX_DIFF_CHARS` fails closed before parsing, in the action and in `scan_diff_text`, even when only lock content is large | Size-cap test with the LLM never called |
| O3 | A file entry with no change, mode or rename information fails closed; mode-only, empty-new-file, empty-deletion and rename entries still scan clean | Parametrised parse and scan tests |
| O4 | The write guarantee (output property plus named bookkeeping keys) is stated in the spec and the action, and a test asserts the written keys are a subset of `{output_key} + LLM_BOOKKEEPING_KEYS` | Spec text, `test_action_routes_and_stores_only_its_output` |
