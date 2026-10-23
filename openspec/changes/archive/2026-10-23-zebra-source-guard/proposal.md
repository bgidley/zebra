## Why

*Read Zebra Source* still fails on guessed paths. After #211 a miss names the nearest files, but
the agent needs a second tool call to read the right one, and many never make it (19 failures in
the dream cycle that raised #223). A path whose top-level entry is not on the allowlist, such as
`zebra_tasks/agent/stuck.py` (missing the `zebra-tasks/` prefix), is refused as "not readable
source" with no suggestions at all. Refusals of `.env` or `../etc/passwd` do not say why, so they
read as bugs. Closes #221, closes #223.

## What Changes

- **Auto-recovery**: when a read path does not exist and exactly one readable file is a
  high-confidence match, `zebra_source` reads that file in the same run. The text starts with a
  note naming both paths, and the output gains `path` (the file actually read). A high-confidence
  match is the only readable file with the same name or, if no file has that name, the only path
  at least 0.9 similar whose file name is also at least 0.85 similar (a long shared directory alone
  scores 0.9). Anything ambiguous still fails with suggestions, as now.
- **Unknown top-level entries are misses, not refusals**: a path under a top-level entry that is
  not on the allowlist and does not exist is handled like any missing path (auto-recovery or
  suggestions). An existing entry that is not on the allowlist (e.g. `legacy/`) is still refused.
- **Refusals say why**: outside the tree → "outside the Zebra source tree"; dot-entries, databases,
  keys and runtime directories → "a hidden, secret or runtime file Zebra never reads".
- *Read Zebra Source* (version 3) describes the auto-recovery.

## Non-goals

- Auto-recovery for `list` or `search` (they already return listings).
- Widening the allowlist or reading anything currently refused.
- Changing `llm_agent` or the *Zebra Source Explorer* workflow.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | A guessed path with one clear match reads in the same run | Tests: a typo (`thng.py`), a wrong directory (`zebra-tasks/thing.py`) and a missing package prefix (`zebra_tasks/thing.py`) each succeed, return the right file's lines with a first-line note naming the requested and actual paths, and set `output.path` |
| O2 | Ambiguous or weak matches never guess | Tests: two same-name files, two paths both ≥ 0.9 similar, and a same-directory path with a dissimilar name (`thx.py` vs `thing.py`) all fail with suggestions, the list/search hint and no content; auto-recovery never reads a dot-entry, database, `tmp/` or symlinked file |
| O3 | Unsafe paths are refused with a reason | Tests: `../etc/passwd` and `/etc/passwd` say "outside the Zebra source tree"; `.env`, `.venv/lib.py`, `*.sqlite3`, `tmp/` say "hidden, secret or runtime"; an existing non-allowlisted entry is still refused; the existing escape tests pass |
| O4 | It works on prod | After deploy, `manage.py run_workflow "Read Zebra Source"` on prod with `zebra_tasks/agent/stuck.py` succeeds with the correction note, and `.env` / `../etc/passwd` fail with the new reasons |
