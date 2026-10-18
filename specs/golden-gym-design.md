# Golden-task gym (#171)

OpenSpec: `openspec/changes/golden-task-gym/` (archived at delivery). GitLab: #171.

## 1. Goal & scope

The Dream Cycle rewrites workflows itself. #128 checks that a rewrite is valid YAML with registered
actions, but not that it still does the job. The gym runs curated **golden tasks** against a
workflow, has an LLM judge score the outputs, and blocks a self-modification that scores worse than
the version it would replace.

**In scope:** golden task files, the `run_golden_gym` action (gate and on-demand modes), optimizer
staging, Dream Cycle v8, the *Golden Gym* system workflow, score storage, the `/gym/` page.

**Out of scope:** gating *new* workflows (nothing to regress from) and in-loop variants
(`workflow_variant_creator` adds a workflow, never replaces one); golden tasks written by Zebra;
prompts outside workflows (#98 should call the same gate when it lands).

## 2. Data model

- **Golden tasks** are files, not rows: `zebra-agent/golden/<id>.yaml` with `id`, `workflow` (name),
  `goal`, `expected`, `criteria` (non-empty list). `ZEBRA_GOLDEN_TASKS_DIR` overrides the directory.
  `zebra_agent/gym.py`: `GoldenTask`, `load_golden_tasks()` (skips invalid files and duplicate ids
  with a warning), `WorkflowLibrary.list_golden_tasks(workflow_name=None)`.
- **`GymScore`** (`zebra_agent/metrics.py`): `id`, `gym_run_id` (the gym task's process), `golden_id`,
  `workflow_name`, `variant` (`current` | `candidate`), `score` (0–1, or None if unscored),
  `error`, `details` (JSON: `criteria` verdicts, `reasoning`, `output_excerpt`, `mode`
  `gate`/`on_demand`, and `decision` for gate runs), `created_at`.
- `MetricsStore.record_gym_scores(scores)` / `get_gym_scores(golden_id, workflow_name, variant,
  limit)` (newest first) in both backends. Django: `GymScoreModel`, table `zebra_gym_scores`,
  migration `0031_gym_scores`. System-level (no user scope), like Dream Cycles.
- Optimizer results gain `pending_gym` (staged modifications: `name`, `original_yaml`,
  `modified_yaml`, `llm_defined`, `reason`, `change`); `continuation_changes` may hold
  `status: pending_gym` until the gym decides.
- Gym task properties across the suspend: `__gym_plan__`, `__gym_runs__` (child id → run). Gym
  children carry `__gym_run__: true`.

## 3. Interfaces

- **Action `run_golden_gym`** (`zebra_tasks/agent/gym.py`), properties: `candidates`
  (pure template, e.g. `{{optimization_results.pending_gym}}`; absent = on demand; when absent a
  `candidates` list in the run's process properties is used), `workflows` (on-demand filter; task
  property or run input), `promote` (true; false = check only), `tolerance` (0.1), `timeout` per run
  (150s), `max_tasks_per_workflow` (3), `max_runs` (12), `model` (judge, `sonnet`), `results_key`
  (`optimization_results`), `output_key` (`golden_gym`). Output `{mode, promote, decisions:
  [{workflow, decision, reason, current_mean, candidate_mean, per_task}], scores, skipped, errors}`.
  Never fails its process. Declare `idempotent: true`.
- **`workflow_optimizer`**: `gym_gate` (false). True and not `dry_run`: *modify* changes go to
  `pending_gym` (still counted toward `max_changes`), not saved, not in `changes_made`.
  `save_workflow_file()` is now a module function shared with the gym.
- `execute_workflow.extract_workflow_output(properties, result_key)` and `OUTPUT_KEYS` are module
  level (shared with the gym).
- **Workflows:** Dream Cycle v8 (`gym_gate: true`, new `golden_gym` step after
  `optimize_workflows`, summary "Golden gym" section). New system workflow *Golden Gym*
  (`golden_gym.yaml`, `result_key: golden_gym`, `promote: false`), run with
  `manage.py run_workflow "Golden Gym" [--input-file -]`; inputs `workflows`, `candidates`.
- **UI:** `/gym/` (`api/gym.py` read model, `pages/golden_gym.html`, nav "Gym"): each golden task's
  latest current-version score and last 10 scores; the last 10 gate decisions with both means.

## 4. Control flow

Start (`subflow_results` is None):
1. Plan. Gate mode: per candidate, the workflow's golden tasks (≤ `max_tasks_per_workflow`).
   None → `promoted`, reason `ungated: no golden tasks`. Else load current (`original_yaml`, or the
   library's YAML when missing) and candidate; reject if either fails `unsafe_reason` (a manual
   task, an unregistered or `always_irreversible` action) or would exceed `max_runs`. The candidate
   definition gets its own id (`<id>-gym-<hex>`): same name + version would otherwise overwrite the
   current definition in the store. On demand: every active library workflow with golden tasks
   (or `workflows`), current version only; unsafe or over-cap tasks are skipped.
2. No runs → finish now. No judge provider → reject gated candidates, finish.
3. Create the children (linked to the task, so the goal queue ignores them), save the plan on the
   task, start them **concurrently** (`asyncio.gather` of `start_child` with `timeout`), fail any
   whose start raised, `TaskResult.suspend(children)`.

Finish (engine re-runs with `subflow_results`): add each child's `__total_cost__` /
`__total_tokens__`; a failed run scores 0; otherwise extract the output (`result_key`, standard
keys, non-internal properties) and judge it concurrently (each criterion 0 / 0.5 / 1, mean; blind to
variant). An unparseable reply or wrong criterion count leaves the score None. Decide each pending
candidate: any run missing or unscored → `rejected`; `mean(candidate) < mean(current) - tolerance`
→ `rejected` (`gym regression: candidate scored X vs current Y`); else `promoted`. Save promoted
candidates (`promote` and a library path), record every score, and in gate mode with `promote`
rewrite `optimization_results`: promoted → `changes_made` + `modified_workflows`, rejected →
`failed_changes`; `pending_gym` emptied; `continuation_changes` updated. Downstream steps (summary,
`/dreams/`, improvement requests) read the final verdict unchanged.

Any exception → every still-pending candidate rejected (`gym error: …`), report returned, step ok.

## 5. Configuration

| Setting | Default | Where |
|---|---|---|
| `ZEBRA_GOLDEN_TASKS_DIR` | `zebra-agent/golden` | env |
| `tolerance` / `timeout` / `max_runs` / `max_tasks_per_workflow` / `model` | 0.1 / 150s / 12 / 3 / sonnet | task properties (Dream Cycle, Golden Gym) |

Budget: prod Dream Cycles take 60–210s of their 600s bound; gym runs and judge calls run
concurrently, so a gated change adds about one workflow run plus one judge call of wall time. Cost per
gated modification: 2 × N runs + 2 × N judge calls (about 700 tokens each), N ≤ 3.

## 6. Open questions / risks

- **Judge noise** may reject a fine change. Mitigated by same-run A/B (model and judge drift cancel)
  and the 0.1 tolerance; a rejected change can be proposed again next cycle. If noise shows up,
  add repeats per task or per-task rules. Measured once on prod's Sonnet: a good answer scored 1.0,
  a degraded one 0.125.
- **Coverage** is only as good as the golden set: four seed tasks (*Answer Question* ×2,
  *Summarize Text*, *Analyze Problem*). Other workflows stay ungated until someone adds tasks.
- **Mean hides one bad task**: a candidate much worse on one task but better on another can pass.
  Accepted for the first slice; `per_task` is recorded so a per-task rule can be added.
