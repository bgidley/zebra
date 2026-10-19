## Why

Zebra's source tools fail about 1 read in 10 on prod (18 of 171 *Read Zebra Source* runs). All 18
asked for files that are in git but not in the image (`specs/…`, `openspec/…`, `scripts/*.sh`,
`AGENTS.md`, `CLAUDE.md`). The bare "'x' is not a file" error gives no way to recover, there is no
way to see what is deployed, and agents retry the same path. Closes #211, closes #212.

## What Changes

- **List operation**: `zebra_source` `operation: list` shows one directory level (subdirectories
  with `/` and their file count, files with their size), or with a `glob`, the matching files
  under that directory. It uses the same allowlist as read and search. A new tool workflow,
  *List Zebra Source*, exposes it.
- **Recoverable read errors**: a missing path fails with a message naming up to 5 nearest existing
  paths (same file name first, then close matches) and a hint to use list or search. A directory
  path gives its listing. A path under an allowlisted entry that is not deployed says so and names
  the top-level entries that are.
- **Docs and specs deployed** (#212): the runtime image also ships `specs/`, `docs/`, `openspec/`,
  `scripts/`, `deploy/` and the root `*.md` files. These are already on the allowlist, so the
  paths agents ask for now exist.
- Tool descriptions name the deployed top-level entries. The outcome review offers the list tool.

## Non-goals

- Writing source, or reading anything outside the current allowlist.
- Fuzzy search inside file contents (search already does regex).

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | Agents can see what source is deployed | Tests: *List Zebra Source* lists a directory one level deep (dirs with `/` and file counts, files with sizes); with a glob (same `fnmatch` rules as search, matched against root-relative paths) it lists matching files recursively, capped at `max_results`; an empty directory and a glob with no matches each say so |
| O2 | A bad path gives the agent a way to recover | Tests: a mistyped file names the right file among at most 5 suggestions and says to use list or search; a file name that exists elsewhere is suggested by its full path; a path with no close match still gets the hint and no bogus suggestions; a directory path returns its listing; a path under an allowlisted entry that is not deployed names the deployed top-level entries |
| O3 | The paths agents asked for read on prod | After deploy, *Read Zebra Source* succeeds on prod for `specs/zebra-as-is.md`, `AGENTS.md`, `CLAUDE.md`, `scripts/zebra-outcome-review.sh` and `openspec/config.yaml` (run via `manage.py run_workflow`) |
| O4 | The sandbox holds for every operation | The existing `test_zebra_source.py` escape and denial tests pass unmodified; new tests show list and suggestions never name dot-entries, `*.sqlite3`, `tmp/` or symlinked files and refuse `..` / absolute paths outside the root; on prod `.env` and `../` are still refused |
| O5 | Source reads stop failing in real use | In this change's own outcome review on prod, at most 1 *Read Zebra Source* run fails, and every failure message carries the list/search hint (baseline: 18 of 171 failed, none with a hint) |
