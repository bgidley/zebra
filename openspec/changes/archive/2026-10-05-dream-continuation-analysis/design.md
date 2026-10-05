## Context

Run lineage lives on `WorkflowRun`: `extends_run_id` (predecessor), `continuation_comment` (#134), `continuation_decision` / `continuation_rationale` (#135). `MetricsStore` offers `get_continuations_since(cutoff)` and `get_run_chain(run_id)` (root → leaf). The dream cycle is `analyze_metrics → load_workflows → evaluate_workflows → optimize_workflows → generate_summary`.

## Goals / Non-Goals

**Goals:** gather chains, find patterns, turn them into concrete optimizer priorities, report them, and expose a per-workflow continuation rate in the analysis output.

**Non-Goals:** no new dream-cycle step, no store contract/schema change, no web UI change (continuation rate is in the analysis output and evaluator prompt only), no LLM call in the analyzer.

## Decisions

- **Extend `metrics_analyzer`, not a new step.** It already owns the window and the store; output gains `continuation_analysis` plus per-workflow `continued_runs` / `continuation_rate`. Gathering is wrapped so any store failure logs a warning and yields an empty block — the rest of the analysis still succeeds.
- **Chains from leaves.** Continuation runs in the window whose id is not another continuation's predecessor are leaves; `get_run_chain(leaf)` gives each chain. Links are deduplicated by continuation run id when counting.
- **Continuation rate** = distinct in-window runs of workflow W that some continuation extends ÷ W's in-window runs.
- **"Where it stopped"** = the root run's task executions: last task, and tasks not `complete`.
- **Added steps** = completed tasks of a continuation run that ran a *different* workflow from its predecessor and whose `task_definition_id` the predecessor did not run; counted per predecessor workflow.
- **Proposals (deterministic):**
  - workflow continued ≥ `min_continuations_for_proposal` (default 2) → `enhance` that workflow; the action cites user comments and added steps;
  - `new_workflow` decision whose continuation run succeeded → promote: `enhance` the continuation workflow (widen `use_when`) if it is in the library, otherwise `create` it.
  - Proposals carry `source: "continuation"`.
- **Evaluator merge.** Proposals are prepended to `improvement_priorities` unless the LLM already proposed the same (type, target); priorities are renumbered.
- **Optimizer.** Unchanged generation/validation path (#128); adds `source` to `changes_made` entries and a `continuation_changes` list (made / failed / skipped) for the summary.
- **Missing fields.** `None` comment/decision/rationale are tolerated: reported as `null`, decision counts use `"unknown"`.

## Risks / Trade-offs

- Proposals from small samples can be noisy → threshold of 2 and the optimizer's `max_changes` cap.
- `get_runs_since` limit (500) bounds the window scan; acceptable for a daily cycle.
