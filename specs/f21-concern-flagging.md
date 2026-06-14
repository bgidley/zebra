# F21: Proactive Concern Flagging (REQ-ETH-004)

## Goal & scope

During planning — *after* a workflow has been selected/created but *before* the
formal `ethics_plan_review` gate — the agent proactively surfaces potential
concerns about the chosen approach (risky/irreversible steps, privacy, scope
creep, side effects, safety). Concerns are **advisory and non-blocking**: they
never route to a rejection branch. They are surfaced on the run-detail page so
the human can see what the agent noticed before/while the plan ran.

This is deliberately distinct from the ethics gates:

- `ethics_input_gate` / `ethics_plan_review` are **blocking** Kantian/values
  checks that route `proceed` / `reject` (F19).
- `flag_concerns` is a **non-blocking, pre-gate scan** that only records concerns.

GitLab issue: [#21](https://gitlab.com/gidley/zebra/-/issues/21).

Out of scope: persisting concerns to the ethics audit trail (F20), blocking
execution, or any human acknowledgement workflow — concerns are display-only.

## Data model changes

No new tables or store interfaces. The concern set lives in process properties:

- `planning_concerns` (set via `output_key`) and the engine-managed
  `__task_output_flag_concerns` both hold the action's result dict:
  ```json
  {"concerns": [{"description": "...", "severity": "low|medium|high", "step": "..."}],
   "summary": "..."}
  ```
- These sit on the **Agent Main Loop (root) process**, alongside `run_id`.

## API / interface changes

- New task action `flag_concerns` (`zebra_tasks.agent.flag_concerns:FlagConcernsAction`),
  registered as a `zebra.tasks` entry point. Inputs: `goal`, `plan_context`,
  `reasoning`, `provider`, `model` (default `haiku`), `output_key`
  (default `planning_concerns`). Always returns `TaskResult.ok` with **no**
  `next_route`. Reversibility hint: `always_reversible`.

## Control flow

`agent_main_loop.yaml` (version 4): the three planning branches
(`use_existing`, `create_workflow`, `create_variant`) now converge on
`flag_concerns` (the synchronized join), which then routes unconditionally to
`ethics_plan_review`:

```
select_workflow ─use_existing─┐
create_workflow ──────────────┤→ flag_concerns → ethics_plan_review → execute_workflow
create_variant ───────────────┘   (advisory)        (blocking gate)
```

`flag_concerns` carries `synchronized: true` (moved off `ethics_plan_review`).

## Surfacing in run detail

`_build_parent_flow_context()` (web_views) already loads the root process's
properties; it now also returns `planning_concerns` via
`_extract_planning_concerns()` (non-empty concerns only). Both `run_detail` and
the `_run_detail_pending_fallback` paths pass it to the template, which includes
`partials/planning_concerns.html` (an amber advisory panel with per-concern
severity badges). Included in both `run_detail.html` and `run_pending.html` so
concerns show while a goal is still running.

## Configuration

None. The advisory scan defaults to the `haiku` model (cheap); overridable via
the task `model` property or the process `__llm_model__`.

## Open questions / risks

- Severity is a free-form `low|medium|high` string from the LLM; not yet tied to
  the trust/reversibility vocabulary.
- Concerns are display-only — no acknowledgement is recorded. If a future
  requirement needs an audit trail of flagged concerns, route them through the
  F20 ethics audit store.
