## Context

The Dream Cycle's `workflow_optimizer` writes modified workflows straight into the library
(`foo_1.yaml`; the newest file wins). #128 made that save conditional on structural validity only.
`TaskResult.suspend` (#146, #181) lets an action start child processes and resume with their
results, which is how the gym runs golden tasks without polling.

Prod Dream Cycles take 60–210s of their 600s `DREAM_CYCLE_TIMEOUT`, so a gym step that runs
its children concurrently (about one workflow run plus one judge call of wall time) fits.

## Goals / Non-Goals

**Goals:** catch a self-modification that makes a workflow worse at its golden tasks before it is
promoted; let a human run the suite on demand; keep score history.

**Non-Goals:** gating *new* workflows (no baseline) or in-loop variants (`workflow_variant_creator`
saves a new workflow; it never replaces one); golden tasks written by Zebra; prompts outside
workflows (Agent SDK self-improvement, #98, is not built; it should call the same gate).

## Decisions

- **Golden tasks are repo files**, `zebra-agent/golden/*.yaml`, one per task, curated by humans
  and reviewed in MRs. `ZEBRA_GOLDEN_TASKS_DIR` overrides the directory. Actions read them via
  `WorkflowLibrary.list_golden_tasks()` (no direct disk reads in actions).
- **Same-run A/B, not a stored baseline.** A gated candidate and the current version run on the
  same golden tasks in the same gym run and are judged the same way, so model drift and judge
  drift cancel out. Costs 2 × N runs; N is capped (`max_tasks_per_workflow`, 3).
- **Absolute, criterion-based judging.** One LLM call per output (default `sonnet`, temperature
  0 where the model accepts it): each criterion scored 0, 0.5 or 1; task score = mean. A failed run
  scores 0. Unparseable judge reply → the score is missing; a candidate with any missing score is
  rejected (fail closed).
- **Decision rule.** Reject when `mean(candidate) < mean(current) - tolerance` (0.1). Otherwise
  promote. Simple; per-task rules can come later if the mean hides regressions.
- **Safety.** The gym only executes definitions whose tasks are all `auto` and whose actions are
  registered and not `always_irreversible`. A gated candidate that fails this check is rejected.
  Golden tasks for unsafe current workflows are skipped with a warning.
- **Staging, not a second save path.** The optimizer (with `gym_gate: true`) puts modify changes
  in `pending_gym`; only the gym saves them, through the optimizer's `save_workflow_file`. The gym
  rewrites `optimization_results` so every reader (summary, `/dreams/`, improvement requests) sees
  the final verdict without changes.
- **Scores in `MetricsStore`** (`GymScore`, new table `gym_scores`), not process properties: the
  `/gym/` history needs per-task queries across gym and dream runs.

## Risks / Trade-offs

- Judge noise can reject a fine change → tolerance 0.1, same-run comparison; a rejected change
  is only deferred, the next cycle can propose it again.
- Golden workflows with side effects → excluded by the safety check; golden tasks should target
  pure LLM/compute workflows.
- Cost: bounded by `max_changes` (3) × N (3) × 2 runs per cycle; typical cycles modify 0–1
  gated workflows.
