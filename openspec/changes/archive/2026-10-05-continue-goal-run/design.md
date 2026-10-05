## Context

F116 added `previous_run_context` (a compact summary of one earlier run) and `WorkflowRun.extends_run_id`. Phase 17 builds on that to make continuation first-class. #134 handles the user-facing continuation and its lineage, #135 chooses how to continue, and #136 learns from chains. All three share the lineage foundation in this branch's first commit.

## Decisions

**Lineage is `extends_run_id`, not a new column.** A continuation is a follow-up with a comment. Reusing F116's link means plain follow-ups also appear in chains, and the dream cycle sees one consistent graph. The fields `continuation_comment`, `continuation_decision` and `continuation_rationale` are what make a link a continuation.

**Chain queries are interface defaults.** `MetricsStore.get_run_chain` walks `extends_run_id` back to the root, oldest first, with cycle and depth guards. `get_continuations_since` filters `get_runs_since`. Both are concrete methods on the ABC, so every backend gets them without extra code. A backend can override them with a single query later if chains grow long.

**Descendants are found in the view.** `_run_chain` combines the ancestors with the continuations started since the viewed run, followed forward breadth-first. This avoids a new store method, and the volume is small (`get_continuations_since` is user-scoped and limited to 500).

**The goal text is unchanged; the comment travels separately.** The continuation process's `goal` is the previous run's full goal, so run records group naturally by goal. The comment is a separate `continuation_comment` property. It is stored only when `previous_run_context` is present, so a stray comment never fakes a continuation. `with_previous_run` reads it to frame the prompt.

**Context stays compact.** Task progress is capped at 20 tasks of 300 characters each. The chain summary is capped at the last 5 links, each with a 200-character goal and a 300-character comment. Each link is a flat summary, never a nested earlier context. Loading task executions or the chain is best-effort: failures fall back to the F116 basic context.

**The API always queues.** `/api/runs/<id>/continue/` creates a daemon-managed CREATED process, which survives redeploys (#129). The web form offers "Continue now", which reuses the `/run/execute/` background path and WebSocket progress, and "Queue".

## Data model

No changes beyond the foundation: `WorkflowRun` and `WorkflowRunModel` gain `continuation_comment` (text), `continuation_decision` (≤32 characters) and `continuation_rationale` (text) in migration 0024. The process properties are `previous_run_context` (now optionally with `tasks`, `chain`, `comment` and `error`) and `continuation_comment`.

## Risks

- Long chains are linear walks of `get_run`, capped at depth 50. That is acceptable at current volumes.
- Continuations of a run whose metrics record is missing (orphaned processes) are not supported. They return 404.
