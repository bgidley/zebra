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
and path suggestions SHALL name only entries a read would allow. It SHALL never write.

#### Scenario: Read a source file
- **WHEN** `zebra_source` reads `zebra-tasks/zebra_tasks/agent/stuck.py` with a line range
- **THEN** it returns those lines prefixed with line numbers, capped at `max_chars`

#### Scenario: Escape attempt
- **WHEN** the path is `../etc/passwd`, `.env`, `zebra-agent-web/db.sqlite3` or an absolute path outside the root
- **THEN** the task fails with a refusal and no content

#### Scenario: Search
- **WHEN** `zebra_source` searches for a regex under a glob
- **THEN** it returns at most `max_results` `path:line: text` hits from allowed files

#### Scenario: List a directory
- **WHEN** `zebra_source` lists `zebra-tasks` (or the root, when no path is given)
- **THEN** it returns that directory's allowed subdirectories, each with `/` and its file count, and its allowed files with their sizes

#### Scenario: List by glob
- **WHEN** `zebra_source` lists with a glob such as `zebra-tasks/**/*.py`
- **THEN** it returns at most `max_results` matching allowed file paths, using the same glob rules as search

#### Scenario: Missing file
- **WHEN** `zebra_source` reads a path that does not exist
- **THEN** the task fails with a message naming up to 5 nearest existing source paths (files with the same name first) and saying to use the list or search tool

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
The `human_ruling` form SHALL show a compact per-outcome summary (id, outcome text, both verdicts,
agreed) and, for each disputed outcome only, its own section with the outcome text and each
reviewer's evidence. It SHALL NOT show earlier tasks' raw outputs. The evidence table posted on the
issue (`table_markdown`) SHALL keep both reviewers' evidence.

#### Scenario: One outcome disputed
- **WHEN** the reviews disagree only on O5
- **THEN** `dispute_notes` has one section, headed with O5 and both verdicts, holding O5's text and Zebra's and Claude's evidence as separate paragraphs

#### Scenario: Summary has no evidence
- **WHEN** the reviews are compared
- **THEN** `summary_markdown` has one row per outcome with id, outcome text, Zebra's verdict, Claude's verdict and agreed, and no evidence

#### Scenario: Ruling page hides prior outputs
- **WHEN** the human opens the `human_ruling` task page
- **THEN** no earlier task output is shown above the form

### Requirement: Human tasks can hide prior outputs
A human task whose properties set `show_prior_outputs: false` SHALL render its form without the
earlier tasks' outputs. Without the property, prior outputs SHALL be shown as before.

#### Scenario: Default names a field of a dict property
- **WHEN** a schema default is `{{review_result.dispute_notes}}` and `review_result` is a dict
- **THEN** the field shows `review_result["dispute_notes"]`

#### Scenario: Property unset
- **WHEN** a human task does not set `show_prior_outputs`
- **THEN** its page shows earlier tasks' outputs above the form
