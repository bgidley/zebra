## Context

`zebra_source` (`zebra_tasks/agent/zebra_source.py`) raises `SourceAccessError` for every refused
or bad request; `run()` turns it into `TaskResult.fail(message + RECOVERY_HINT)`. Tool workflows
(*List / Read / Search Zebra Source*) reach `llm_agent` as a failed child whose error text becomes
the tool result, so the error text is the only channel to the caller.

## Decisions

- **Tag in the text, at the start.** `[reason] message. hint`. The start is what a model or a regex
  sees first; the end stays the recovery hint (#211).
- **Five reasons.** `protected`: outside the tree, hidden/secret/runtime, or an existing top-level
  entry off the allowlist. `not_deployed`: an allowlisted top-level entry absent from this tree
  (e.g. `specs/` outside the image). `missing`: anything else that does not exist. `invalid`: a bad
  request (no path/pattern, bad regex or glob, directory to `read`, file to `list`, too large).
  `error`: an `OSError` while reading.
- **Reason is required** on `SourceAccessError`, so a new raise site cannot forget it.

## Risks

- Callers matching on the start of the old message break; only our own tests did (updated).
- The #255 branch changes the "file passed to `list`" path; whichever merges second keeps the tag.
