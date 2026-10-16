## Context

Delivery today: implement → `zebra-feedback.sh` (Zebra reviews a bullet list) → CI → merge →
deploy. See `specs/outcome-review-design.md` for the narrative design.

## Decisions

**Outcomes live in the proposal and the issue.** `openspec/config.yaml` requires an `## Outcomes`
table (`#`, outcome, how we'll know). The session posts it on the issue (`glab issue note`). There
is no approval gate.

**Review is a Zebra workflow, run directly.** `Outcome Review` declares required `inputs`, so it is
tool-only and never picked for a goal. `manage.py run_workflow "Outcome Review" --input-file -`
creates and starts the process with a `run_id`, so it shows on the Activity page. It prints
`{status, process_id, run_id, task_id, output, error}`; `--status <process_id>` re-reads it later.
Status is `complete`, `awaiting_input`, `failed` or `running`.

**Flow.** `zebra_review` (llm_agent, tools *Read Zebra Source* / *Search Zebra Source*, JSON) →
`compare` (`compare_outcome_reviews`) → route `agreed` → done; `disputed` → `zebra_reconsider`
(llm_agent, sees Claude's notes for the disputed outcomes) → `compare_again` → `agreed` → done;
`disputed` → `human_ruling` (auto: false) → `record_ruling` (`compare_outcome_reviews` with
`ruling_key`). Zebra never sees Claude's verdicts before its first review.

**Verdict format.** Both sides use `{"verdicts": [{"id": "O1", "verdict": "met|partial|missed",
"evidence": "..."}], "summary": "..."}`. Agreement means equal verdicts per outcome id. A missing or
unparseable verdict counts as a disagreement, never as agreement. The comparison writes
`review_result = {status: agreed|disputed|ruled, rows, disputed, followups, table_markdown,
ruling?}`; `followups` lists the outcomes agreed as partial or missed.

**Source access.** The `zebra_source` action has `operation: read | search`. Its root is
`ZEBRA_SOURCE_ROOT`, or by default the directory three levels above the installed `zebra_tasks`
package: `/app` in the prod image, the repo root locally. Paths must resolve inside the root and
under an allowlisted top-level entry (the four packages, `specs`, `openspec`, `docs`, `scripts`,
top-level `*.md`, `pyproject.toml`, `version.json`). Denied: dot-entries (`.env`, `.venv`, `.git`),
`*.sqlite3`, `tmp/`, `staticfiles/`, `__pycache__`. Reads are capped (default 12000 chars, with a
line range); search returns at most 50 `path:line: text` hits. `reversibility_hint` is
`always_reversible`.

**Diff transport.** The prod image has no `.git`. The script builds the diff on the host
(`git diff <base>..<head>`, capped at 60000 chars) and sends it with the outcomes and Claude's
review as JSON on stdin.

**Script exit codes.** `zebra-outcome-review.sh`: 0 when the review is complete (agreed or ruled),
2 while it waits on a human, 1 on failure. `--status <process_id>` polls. Unlike
`zebra-feedback.sh`, it does not exit 0 on failure: a review that cannot run blocks sign-off, and
the session says so.

## Interfaces

- Actions: `zebra_source`, `compare_outcome_reviews` (entry points in `zebra-tasks`).
- Workflows: `outcome_review.yaml`, `read_zebra_source.yaml`, `search_zebra_source.yaml`.
- Command: `run_workflow`.
- `specs/zebra-as-is.md`: tooling/process section, task actions list, workflows list.

## Risks

- The LLM may return malformed JSON. The comparison treats it as disputed, so the failure mode is
  a human task, not a false pass.
- Cost: two llm_agent passes on Sonnet, a few cents per feature.
