## Context

#251 makes Zebra deliver changes to its own code through its own workflows. Slice A (archived
`2026-10-29-builder-stages`) gave the host builder delivery stages with per-stage credentials and
host-checked results. The user decided: the sandbox follows CLAUDE.md itself, Zebra orchestrates
and recommends, and there is **one** human task, the GitHub PR review with Zebra's recommendation.

## Decisions

**One workflow, stage per builder job.** Improve Zebra is a plain YAML workflow: each stage is a
`claude_code_build` (stage, issue, branch `f<issue>/improve-zebra`) followed by the existing
`external: builder` wait that `BuilderWatcher` completes. No new engine or watcher code. The
branch name is fixed per issue so a rerun or a `changes` round resumes the same branch.

**Zebra's two judgements are `llm_agent` steps over its own source**, as in Outcome Review:
- `outcome_feedback` (text) replaces `scripts/zebra-feedback.sh` for this path; it is advisory and
  is passed to the ship stage, which adjusts the outcomes only for a real gap.
- `recommend` (JSON) sees only host-checked facts: pipeline status, changed and sensitive files,
  and the branch diff (`diff_excerpt`, added to the builder's propose/ship results from the same
  compare call it already makes). It must not recommend merge unless the pipeline is `success`.

**One human task.** `review_pr` shows the PR, pipeline, sensitive files, Zebra's recommendation
and its outcome feedback; its buttons are the routes. `changes` routes back to `ship`; the next
ship prompt carries `{{__task_output_review_pr.feedback}}` (empty on the first round, as a missing
template key resolves to ""). Until slice C, `merge` ends at the report and the human merges.

**Dream wiring without conditional routes.** The engine fails a task whose route matches no
routing, so the request workflow does not branch: `start_improvement_build` always runs after
`file_issue` and decides itself (verdict `build` and a known issue → start; else skip). It
starts the process unlinked and immediately, as `propose_zebra_improvements` does, so the daemon
never sees it as a queued goal.

**System workflows are off-limits to the dream cycle.** `is_system_workflow(name, tags)` (core
names or the `system` tag) is shared by the loader and the curator. The optimizer only modifies
workflows the loader gave it, so that covers edits; creating a workflow under a system name would
shadow it (newest file wins, #224), so `_validate_workflow_yaml` rejects that by reading the
existing workflow's tags (`is_system_workflow_name`).

## Interface / data changes

- Workflow `Improve Zebra` v1 (`system`, `inputs.required: [issue]`); process properties
  `propose_job`, `ship_job`, `outcome_feedback`, `recommendation`, `answer`.
- `Zebra Improvement Request` v3: verdict `build`; task `start_build`; property
  `improvement_build` = `{process_id, issue}` | `{skipped}` | `{error}`.
- Action `start_improvement_build` (entry point). `ACCEPTED_VERDICTS`, `issue_iid()`.
- Builder stage results: `diff_excerpt`, `diff_truncated`.
- `load_definitions.is_system_workflow()`, `is_system_workflow_name()`, `SYSTEM_TAG`.

`specs/zebra-as-is.md` (builds row, dream improvement requests, system workflows) and a new
`specs/self-improvement-design.md`.

## Risks

- A recommendation is an LLM judgement on a capped diff; the human still reads the PR. The prompt
  forbids `merge` when the pipeline is not green or the diff was cut where it matters.
- Claude Code's subscription limits: a ship stage with CI waits can run long (budget 200 turns /
  90 min, the builder ceilings).
- Two runs for the same issue share a branch; not prevented (non-goal).
- If the recommendation step itself fails (unusable JSON after its retry, provider error) the
  process fails after a long build; the PR is still open for a manual review. Rare given
  `answer_on_budget` and the JSON retry; a non-fatal fallback is a follow-up if it happens.
