## Why

The #236 outcome review (2026-11-06) cost $3.11, all on `anthropic/claude-fable-5.1`. The run that
succeeded took 12 model calls, and its prompt grew from 27k to 81k tokens (594k input tokens in all).
Tracing that run's tool calls showed most turns were wasted (GitLab #285):

- **Read Zebra Source is broken on prod.** The dream copy `read_zebra_source_1.yaml` (v10, written
  2026-11-01) ignores the line range: every read returns the file from line 1, cut off at 12k
  characters. Six reads of the same test file each returned the same opening.
- **About 8 calls returned nothing.** Brace globs (`*{skill,sync}*.py`) are not supported, and the
  prod List v3 dream copy says to put globs in `path`, which the action treats as a directory.
- **About half the turns went on finding the tests** the diff already contained.
- **The budget is generous:** `max_tool_turns: 12`.

## What Changes

- **Read Zebra Source v11.** The built-in ships at v11 with its v9 steps, above the dream copy, so
  `copy_builtin_workflows` reinstalls it and retires the copy (#224, #249). List Zebra Source v4
  and Search Zebra Source v3 replace their prod versions the same way and document the glob syntax.
- **Globs.** `zebra_source` expands `{a,b}` alternatives (nested too) in every glob. A list whose
  `path` contains glob characters, with no `glob`, lists by that glob.
- **Change map.** `scripts/zebra-outcome-review.sh` sends a `change_map` input: each changed file
  with its added/removed line counts, then the test functions the diff adds or changes, by file.
  Outcome Review v5 puts it ahead of the diff and tells the agent to start from it.
- **Budget.** Outcome Review v5 lowers `zebra_review` to 8 tool turns and `zebra_reconsider` to 5,
  and tells the agent to read line ranges, not whole files, and to batch its calls.

Not in scope: gating dream changes to tool workflows (#252), and the review model choice (still
`ZEBRA_REVIEW_MODEL`).

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `zebra-source-access`: brace globs, a glob given as list `path`, range reads through the workflow
- `outcome-review`: change map, tighter tool budget

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | On prod, Read Zebra Source with `start_line`/`end_line` returns exactly those lines, because built-in v11 replaced the dream copy | Workflow test of a range read through `read_zebra_source.yaml`; after deploy, prod's active Read Zebra Source is v11 and the dream copy is in `retired/`; a prod range read returns the requested lines |
| O2 | Brace globs and a glob given as List's `path` return matching files instead of nothing | `zebra_source` unit tests (list and search, nested braces, glob as path); List v4 / Search v3 active on prod |
| O3 | Zebra's review prompt starts with a change map of the changed files and the test functions added or changed | Script test: `change_map` in the workflow input lists files with +/- counts and the test names; workflow test that it reaches the prompt |
| O4 | The review runs with a tighter budget: 8 tool turns for `zebra_review`, 5 for `zebra_reconsider`, with guidance to read ranges and batch calls | Outcome Review v5 YAML and a test pinning the turn limits |
| O5 | This change's own outcome review spends clearly less than #236's: under half its 594k input tokens | `LLMSpendModel` rows for this change's Outcome Review process, compared with process `71a950e5` |
