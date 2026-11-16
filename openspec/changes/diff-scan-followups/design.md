## Lock-file tuning (#301)
Measured on `uv.lock` (2001 lines): untuned, 73 findings (`ip_address` 59 from four-part versions,
`card_number` 8 and `phone` 6 from digit runs in package URLs, hashes and dated versions). For lock
lines only, URLs (`_URL_PATH_RE`), 32+ hex digests and `version = "..."` values are blanked before
the rules, and `ip_address` is dropped. Result: clean. Emails, postcodes, phones outside those
spans and confidential patterns still fire. Lock lines remain out of the LLM payload.

## Size cap and malformed entries (#302)
`MAX_DIFF_CHARS` is a module constant checked first in `_rule_scan` (so `scan_diff_text` gets it
too). `DiffFile.changed` is set by a hunk, binary patch, or a mode / rename / copy / similarity
line; `parse_diff` raises `DiffParseError` for any file left unchanged (`index`, `---`, `+++` alone
do not count).

## Write guarantee (#303)
`get_llm(model, context)` records usage via `record_usage`, writing `__total_tokens__`,
`__total_cost__`, `__token_history__`. Kept as is (the project-wide cost path); named in
`LLM_BOOKKEEPING_KEYS`. Hint stays `always_reversible`: the writes stay in the run.
