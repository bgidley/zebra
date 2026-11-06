## Context

The outcome review's `zebra_review` step is an `llm_agent` with three source tools (List, Read and
Search Zebra Source), each a one-step workflow over the `zebra_source` action. Every turn resends
the whole conversation, so a turn that returns a large useless result costs tokens on every later
turn. Prod runs dream-cycle copies of all three tools: Read v10 (range ignored), List v3 (drops
the `glob` input, says to put globs in `path`) and Search v2 (the same as the built-in).

## Decisions

- **Restore by version bump, not by deleting files.** `copy_builtin_workflows` installs a
  built-in whose version is higher than the active copy and retires every other file with that
  name (#224). The new versions are Read v11, List v4, Search v3 and Outcome Review v5. This is
  the fix used for #249. Preventing the dream cycle from breaking tools again is #252.
- **Brace expansion in `_glob_match`.** `fnmatch` has no `{a,b}`. `expand_braces()` repeatedly
  expands an innermost `{…,…}` group into plain globs (nested groups work), up to
  `MAX_BRACE_EXPANSIONS` (64) so a pathological pattern cannot blow up; results are cached. Matching is any-of. List and search share it.
- **A glob in `path`.** If list's `path` contains `*`, `?`, `[` or `{` and there is no `glob`, it
  lists by `path` as a glob from the root. This is what the model and the List v3 copy both do.
- **Change map in the script, not a new action.** The diff is already built in the script's
  Python step. The map is computed there from the diff text (stdlib only, host `python3`), so no
  new task action, registration or reversibility hint is needed. It covers every file even when
  the diff itself is cut at `MAX_DIFF_CHARS`. Test functions: `+` lines matching
  `(async )?def test_\w+` in files under a `tests/` directory or named `test_*.py`. The map is
  capped at 8000 characters.
- **Old callers.** `change_map` is optional in the Outcome Review inputs. The prompt reads
  `{{change_map}}`, which resolves to empty when it is not given.

## Risks

- A built-in at a higher version again becomes the dream cycle's next parent, so the cycle can
  break it again until #252 lands.
- Turn limits that are too tight give a weaker review. `answer_on_budget` still produces an
  answer, and 8 turns was more than the successful #236 run needed once its wasted reads are
  removed.
