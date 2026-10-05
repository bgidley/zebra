## Why

Once a goal has run, the user often wants to carry on from where it got to: a failed run, a partial result, or a "now do the next bit". F116 (#116) lets a *new* goal attach a previous run as context. Continuation is not yet first-class, though. There is no "continue" action on the run itself, failed runs aren't framed as something to pick up, and the next run only sees the previous output, not how far the workflow got. The lineage stops at one hop, so neither the user nor the dream cycle (#136) can see a whole chain. Part of #134 (phase 17 — goal continuation).

## What Changes

- **Continue action.** A "Continue this run" form on the run detail page takes a comment on where the run got to and what to do next. The user can run the continuation now or queue it for the daemon. `POST /runs/<id>/continue/` (web) and `POST /api/runs/<id>/continue/` (API, which always queues) work for successful and failed runs alike, as long as the run is finished and owned by the user.
- **Continuation properties.** The continuation keeps the original goal text. The comment is stored as the `continuation_comment` process property next to `previous_run_context`. Both recorders copy it onto `WorkflowRun.continuation_comment`, as part of the shared lineage foundation in this branch.
- **Richer context.** `load_previous_run_context()` builds `previous_run_context` from the metrics store. It includes task-level progress (task, state, truncated output or error; up to 20 tasks) and a compact summary of earlier runs in the chain (the last 5 links; goal, workflow, outcome, comment). These summaries are never nested. `with_previous_run()` leads with the user's comment, then lists the progress and the earlier runs.
- **Chain display.** The run detail page shows the whole chain (original → continuation 1 → …) from any run in it, including continuations started *after* the viewed run. Each continuation's comment is shown, along with its decision and rationale once #135 populates them. The display lives in `partials/run_chain.html`.

## Capabilities

### New Capabilities
- `goal-continuation`: continue a finished run with a progress comment, enriched continuation context, and a persisted, visible run chain.

### Modified Capabilities
<!-- goal-follow-up behaviour is unchanged: plain follow-ups keep their F116 shape and wording. -->

## Non-goals

- Choosing *how* to continue (same, different existing, or new workflow). That is #135, which writes `continuation_decision` and `continuation_rationale`.
- Dream-cycle analysis of continuation chains, which is #136.
- Continuing orphaned processes that never produced a `WorkflowRun` record.

## Impact

- `zebra-tasks`: `agent/followup.py` (`load_previous_run_context`, enriched `build_previous_run_context` and `with_previous_run`).
- `zebra-agent`: the `AgentLoop.process_goal(continuation_comment=...)` parameter.
- `zebra-agent-web`: the `queue_goal(continuation_comment=...)` parameter, the `run_continue` web view and API view, the `/runs/<id>/continue/` and `/api/runs/<id>/continue/` routes, `ContinueRunRequestSerializer`, and the `partials/run_chain.html` and `partials/run_continue.html` templates.
- Foundation commit (shared with #135 and #136): `WorkflowRun.continuation_comment`, `continuation_decision` and `continuation_rationale`, migration 0024, `MetricsStore.get_run_chain` and `get_continuations_since`.
