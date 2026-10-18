## Why

The Dream Cycle rewrites workflows on its own. Since #128 a rewrite must parse, validate and use
registered actions before it is saved, but nothing checks that the rewrite still does the job.
A prompt edit that makes "Answer Question" worse is saved as long as the YAML is valid, and the
next goal uses it. Zebra itself asked for "a golden-task regression suite, so self-improvement
(#98) can't quietly make me worse". Issue #171.

## What Changes

- **Golden tasks**: curated YAML files in `zebra-agent/golden/`, one per task: the workflow it
  exercises, a goal, the expected outcome and scoring criteria. Loaded through
  `WorkflowLibrary.list_golden_tasks()`.
- **`run_golden_gym` action**: runs golden tasks as child processes (started together, then the
  task suspends on them), has an LLM judge score each output against its criteria (0 to 1), and
  records every score in the `MetricsStore`.
  - **Gate mode** (`candidates`): for each staged workflow modification, runs the current version
    and the candidate on the workflow's golden tasks. The candidate is promoted (saved) unless its
    mean score is more than `tolerance` (0.1) below the current version's. A regression is
    rejected and reported in `failed_changes`. A modification with no golden tasks is promoted
    unchanged (`ungated`). A gated candidate the gym cannot run safely (human tasks, irreversible
    actions) or judge (no LLM) is rejected: the gate fails closed.
  - **On-demand mode** (no candidates): scores the current version of every workflow that has
    golden tasks. Candidates passed as run inputs are checked without being saved.
  - Runs start concurrently, each bounded by `timeout` (150s), capped at `max_runs` (12) per gym.
- **Optimizer staging**: `workflow_optimizer` gains `gym_gate`. When true, a *modify* change is
  staged in `pending_gym` instead of being saved; the gym promotes or rejects it and moves it into
  `changes_made` / `modified_workflows` or `failed_changes`. New workflows (*create*) are not gated:
  there is no current version to regress from.
- **Dream Cycle v8**: `golden_gym` step after `optimize_workflows`; the summary reports gym
  verdicts.
- **Golden Gym** system workflow for on-demand runs (`manage.py run_workflow "Golden Gym"`).
- **Score history**: `GymScore` records (`MetricsStore.record_gym_scores` / `get_gym_scores`),
  Django model + migration, and a `/gym/` page: golden tasks with their latest score, score
  history, and recent gate decisions.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | A deliberately degraded modification of a workflow that has golden tasks is rejected by the gym and not saved | Unit test: degraded candidate → `failed_changes` with both scores, no file written. Prod: `manage.py run_workflow "Golden Gym"` with a hand-degraded *Answer Question* as a check-only candidate reports `rejected` (seed golden tasks ship for *Answer Question*, *Summarize Text* and *Analyze Problem*) |
| O2 | A modification scoring no more than the tolerance (0.1) below the current version, or one with no golden tasks, is still promoted as before | Unit tests for equal/better and ungated candidates: saved, listed in `changes_made` |
| O3 | The gym runs on demand with no human input and scores the current version of every workflow with golden tasks | `manage.py run_workflow "Golden Gym"` on prod completes and writes one `gym_scores` row per golden task |
| O4 | The human can see each golden task's latest score and the last gate decision | `/gym/` on prod lists each golden task with its latest score (and recent scores), and recent decisions with both scores |
| O5 | The gate fails closed: a gated candidate that cannot be run safely or scored is rejected, and the Dream Cycle does not fail | Unit tests: no LLM, unparseable judge reply, child timeout/crash, manual task or irreversible action in the candidate → rejected; cycle step returns ok |
| O6 | The Dream Cycle stays inside its 600s bound with the gym step | Children run concurrently with a per-run timeout (150s) and a cap on runs per gym (12); a prod Dream Cycle completes in under 600s |

## Capabilities

### New Capabilities
- `golden-task-gym`: golden tasks, LLM-judged scoring, a promotion gate for self-modified
  workflows, on-demand runs and score history.

### Modified Capabilities
<!-- none -->

## Impact

- `zebra-agent`: `zebra_agent/gym.py` (golden task loader), `golden/*.yaml`, `GymScore`
  (metrics.py), `MetricsStore` methods + in-memory backend, `WorkflowLibrary.list_golden_tasks`,
  `workflows/dream_cycle.yaml` v8, new `workflows/golden_gym.yaml`.
- `zebra-tasks`: new `agent/gym.py` (`run_golden_gym`) + entry point; `optimizer.py` (`gym_gate`,
  shared `save_workflow_file`); `execute_workflow.py` (shared output extraction).
- `zebra-agent-web`: `GymScoreModel` + migration, `DjangoMetricsStore`, `/gym/` page + nav.
- Cost: per gated modification, 2 × N workflow runs + 2 × N judge calls (N ≤ 3 golden tasks per
  workflow); on-demand, N runs + N judge calls per golden task.
