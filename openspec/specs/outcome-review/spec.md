# outcome-review Specification

## Purpose
Review every non-trivial change against outcomes agreed at its start: after deploy, Zebra (reading
its own source) and Claude review blind, compare, and escalate lasting disagreement to a human.

## Requirements

### Requirement: Proposals record key outcomes
Every non-trivial OpenSpec proposal SHALL contain an `## Outcomes` section listing 3–5 observable
outcomes, each with how it will be checked, and the session SHALL post them on the GitLab issue
before implementation. Trivial changes (docs-only, one-line fixes) are exempt.

#### Scenario: New feature proposal
- **WHEN** a session creates an OpenSpec proposal for a non-trivial change
- **THEN** the proposal has an `## Outcomes` table and the same outcomes appear as a note on the issue

### Requirement: Zebra reviews its own deployed source
The `zebra_source` action SHALL read files, search for regex matches and list directories within
the source root only, under allowlisted top-level entries, and SHALL refuse dot-entries,
`*.sqlite3` files and paths that resolve outside the root (including via `..` or symlinks). Listings
and path suggestions SHALL name only entries a read would allow. A refusal SHALL say whether the
path is outside the tree or a hidden, secret or runtime file. A read of a missing path with exactly
one high-confidence match SHALL read that file in the same run with a correction note. It SHALL
never write.

#### Scenario: Read a source file
- **WHEN** `zebra_source` reads `zebra-tasks/zebra_tasks/agent/stuck.py` with a line range
- **THEN** it returns those lines prefixed with line numbers, capped at `max_chars`

#### Scenario: Escape attempt
- **WHEN** the path is `../etc/passwd` or an absolute path outside the root
- **THEN** the task fails with no content and a message saying the path is outside the Zebra source tree

#### Scenario: Hidden or secret file
- **WHEN** the path is `.env`, under `.venv/`, a `*.sqlite3` file or under `tmp/`
- **THEN** the task fails with no content and a message saying it is a hidden, secret or runtime file Zebra never reads

#### Scenario: Search
- **WHEN** `zebra_source` searches for a regex under a glob
- **THEN** it returns at most `max_results` `path:line: text` hits from allowed files

#### Scenario: List a directory
- **WHEN** `zebra_source` lists `zebra-tasks` (or the root, when no path is given)
- **THEN** it returns that directory's allowed subdirectories, each with `/` and its file count, and its allowed files with their sizes

#### Scenario: List by glob
- **WHEN** `zebra_source` lists with a glob such as `zebra-tasks/**/*.py`
- **THEN** it returns at most `max_results` matching allowed file paths, using the same glob rules as search

#### Scenario: Missing file with one clear match
- **WHEN** `zebra_source` reads a path that does not exist and exactly one readable file has the same name, or none has the same name and exactly one path is at least 0.9 similar with a file name at least 0.85 similar
- **THEN** it reads that file, its text starts with a note naming the requested and the actual path, and `output.path` is the actual path

#### Scenario: Missing file
- **WHEN** `zebra_source` reads a path that does not exist and has no single high-confidence match
- **THEN** the task fails with a message naming up to 5 nearest existing source paths (files with the same name first) and saying to use the list or search tool

#### Scenario: Unknown top-level entry
- **WHEN** the path's top-level entry is not allowlisted and does not exist, e.g. `zebra_tasks/agent/stuck.py`
- **THEN** it is handled as a missing file, not refused

#### Scenario: Path under an entry that is not deployed
- **WHEN** the path's top-level entry is allowlisted but absent from the source root
- **THEN** the failure message names the top-level entries that are present

#### Scenario: Directory read
- **WHEN** `zebra_source` reads a path that is a directory
- **THEN** the task fails with a message containing that directory's listing

### Requirement: Outcome Review compares two blind reviews
The *Outcome Review* workflow SHALL run Zebra's review without access to Claude's verdicts, compare
the two per outcome, and complete with `review_result.status = agreed` when every outcome has the
same verdict from both reviewers. Agreed partial or missed outcomes SHALL be listed in `followups`.

#### Scenario: Reviewers agree
- **WHEN** Zebra's verdicts match Claude's for every outcome
- **THEN** the process completes without a human task and `review_result` holds the reconciled table

#### Scenario: Malformed review
- **WHEN** either review is not parseable or omits an outcome
- **THEN** that outcome counts as disputed

#### Scenario: Outcome neither reviewer judged
- **WHEN** an outcome id in the outcomes table is missing from both reviews
- **THEN** it is listed as disputed, never agreed

### Requirement: Disagreement escalates to a human
When the reviews disagree, Zebra SHALL reconsider the disputed outcomes once with Claude's evidence.
If any outcome is still disputed, the workflow SHALL park on a human task showing both positions,
and SHALL complete with `review_result.status = ruled` and the human's ruling once it is submitted.

#### Scenario: Zebra changes its mind
- **WHEN** the reconsidered verdicts match Claude's
- **THEN** the process completes as agreed with no human task

#### Scenario: Still disputed
- **WHEN** the reconsidered verdicts still differ
- **THEN** the process waits on the `human_ruling` task, and on submission completes with status `ruled`

### Requirement: Workflows can be run directly and polled
`manage.py run_workflow <name>` SHALL create and start the named workflow with properties read as
JSON, and print `{status, process_id, run_id, task_id, output, error}`, where status is `complete`,
`awaiting_input`, `failed` or `running`. `--status <process_id>` SHALL report the same for an
existing process.

#### Scenario: Run parks on a human task
- **WHEN** the workflow stops on an `auto: false` task
- **THEN** the command prints status `awaiting_input` with that task's id and exits 0

#### Scenario: Unknown workflow
- **WHEN** no workflow has that name
- **THEN** the command prints status `failed` with an error and exits 1

### Requirement: Ruling form is readable
The `human_ruling` form SHALL be generated per review (`review_result.ruling_form`). It SHALL list
the agreed outcomes in one line and give each disputed outcome its own read-only section (outcome
text, the crux when briefed, both verdicts each with a one-sentence position, and what would settle
it), immediately followed by that outcome's pick. The full evidence of every disputed outcome SHALL
stay on the page as the last panel. It SHALL NOT show earlier tasks' raw outputs, and reviewer or
brief text SHALL NOT be resolved as `{{templates}}`. The evidence table posted on the issue
(`table_markdown`) SHALL keep both reviewers' evidence.

#### Scenario: One outcome disputed
- **WHEN** the reviews disagree only on O5
- **THEN** the form has `agreed` listing the others, then `O5_case`, `O5` and `O5_note`, then `notes` and `evidence`, and `dispute_notes` has one section for O5 with both reviewers' evidence

#### Scenario: Summary has no evidence
- **WHEN** the reviews are compared
- **THEN** `summary_markdown` has one row per outcome with id, outcome text, Zebra's verdict, Claude's verdict and agreed, and no evidence

#### Scenario: Ruling page hides prior outputs
- **WHEN** the human opens the `human_ruling` task page
- **THEN** no earlier task output is shown above the form

#### Scenario: Reviewer text holds a template
- **WHEN** a reviewer's evidence contains `{{__secret__}}`
- **THEN** the form shows it literally (as `{ {__secret__} }`) and resolves nothing

#### Scenario: Narrow screen
- **WHEN** the ruling page is opened at 390px or 1280px wide
- **THEN** the page does not scroll sideways

### Requirement: Human tasks can hide prior outputs
A human task whose properties set `show_prior_outputs: false` SHALL render its form without the
earlier tasks' outputs. Without the property, prior outputs SHALL be shown as before.

#### Scenario: Default names a field of a dict property
- **WHEN** a schema default is `{{review_result.dispute_notes}}` and `review_result` is a dict
- **THEN** the field shows `review_result["dispute_notes"]`

#### Scenario: Property unset
- **WHEN** a human task does not set `show_prior_outputs`
- **THEN** its page shows earlier tasks' outputs above the form

### Requirement: The review starts from a change map
`scripts/zebra-outcome-review.sh` SHALL send a `change_map` input listing every changed file with
its added and removed line counts, then the test functions the diff adds or changes, grouped by
file, capped at 8000 characters. The Outcome Review prompt SHALL show it before the diff.

#### Scenario: Map of a change with tests
- **WHEN** the reviewed diff changes `a.py` and adds `test_one` and `test_two` to `tests/test_a.py`
- **THEN** `change_map` lists both files with their `+`/`-` counts and names both tests under `tests/test_a.py`

#### Scenario: Map survives a cut diff
- **WHEN** the diff is longer than `MAX_DIFF_CHARS`
- **THEN** `change_map` still lists every changed file

### Requirement: The review has a tight tool budget
The Outcome Review `zebra_review` step SHALL allow at most 8 tool turns and `zebra_reconsider` at
most 5, both with `answer_on_budget`, and their system prompts SHALL tell the agent to start from
the change map, read line ranges rather than whole files, and ask for several reads in one turn.

#### Scenario: Budget limits
- **WHEN** the Outcome Review workflow is loaded
- **THEN** `zebra_review.max_tool_turns` is 8 and `zebra_reconsider.max_tool_turns` is 5

### Requirement: Disputes are briefed without taking a side
When the reviews still disagree after reconsidering, `brief_outcome_disputes` SHALL make one
low-tier LLM call over both reviewers' evidence for the disputed outcomes only, and store per
outcome a crux, each side's position, and what would settle it in `review_result.briefs`. A brief
field that recommends a verdict or says which reviewer is right SHALL be dropped, and a brief
without a crux SHALL be dropped whole. The action SHALL never fail: without a brief the form shows
the first sentence of each side's evidence. The form SHALL label a brief as a model summary, not a
verdict.

#### Scenario: Brief succeeds
- **WHEN** the model returns a crux for O2
- **THEN** O2's section shows "In dispute:" with that crux, both positions and what would settle it

#### Scenario: Brief takes a side
- **WHEN** a brief field says "Zebra is right" or "this should be partial"
- **THEN** that field is dropped, and the brief is dropped if it was the crux

#### Scenario: Brief unavailable
- **WHEN** there is no LLM, the call raises, or the reply has no usable brief
- **THEN** the task succeeds with an `error`, `briefs` is empty, and the form still asks for a ruling

#### Scenario: Reviewers agree
- **WHEN** the reviews agree on the first or second comparison
- **THEN** no brief call is made

### Requirement: The human rules each disputed outcome
The ruling form SHALL have one required met / partial / missed pick per disputed outcome, labelled
with who gave each verdict ("Partial (Zebra)", "Met (Claude)", plain "Missed"), and an optional
note. On submission `review_result` SHALL record each pick as that row's `ruling` (and
`ruling_note`), add ruled partial or missed outcomes to `followups`, write `ruling` as one line per
outcome, list disputed outcomes without a pick in `unruled`, and add a Ruling column to
`table_markdown`. `zebra-outcome-review.sh` SHALL ask the session to read the ruling only for
`unruled` outcomes.

#### Scenario: Submission without a pick
- **WHEN** the human submits without choosing a verdict for a disputed outcome
- **THEN** the submission is refused and the task stays READY

#### Scenario: Ruled partial
- **WHEN** the human picks partial for O1 with the note "no test"
- **THEN** the review completes `ruled`, `followups` contains O1, `ruling` is "O1: partial: no test", and the issue table's Ruling column shows it

#### Scenario: No readable verdicts
- **WHEN** neither review could be read
- **THEN** the form asks for one free-text `ruling`, which is recorded as is with the outcomes `unruled`
