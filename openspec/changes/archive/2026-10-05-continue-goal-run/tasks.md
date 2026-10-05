> Branch: `f134/continue-goal-run`. Reference `#134` in commits.

## 1. Lineage foundation (shared with #135 and #136)

- [x] 1.1 `WorkflowRun` gains `continuation_comment`, `continuation_decision` and `continuation_rationale`; `WorkflowRunModel` gets the same plus migration 0024; both metrics stores updated
- [x] 1.2 `MetricsStore.get_run_chain` and `get_continuations_since` as interface defaults
- [x] 1.3 `followup` continuation keys plus `continuation_fields()`, copied onto run records by `assess_and_record` and `record_metrics`

## 2. Continuation context

- [x] 2.1 `build_previous_run_context` accepts task executions and the chain (capped summaries)
- [x] 2.2 `load_previous_run_context(metrics, run_id)`: finished runs (success or failure); best-effort progress and chain
- [x] 2.3 `with_previous_run` leads with `continuation_comment`, then task progress and earlier runs
- [x] 2.4 `AgentLoop.process_goal` and `queue_goal` accept `continuation_comment` (stored only with a previous run)

## 3. Entry points

- [x] 3.1 Web `POST /runs/<id>/continue/` (`run_continue`): comment required; mode `now` or `queue`
- [x] 3.2 API `POST /api/runs/<id>/continue/`: queues; 202 / 400 / 404
- [x] 3.3 The F116 execute and queue paths use `load_previous_run_context`, so plain follow-ups also get progress

## 4. UI

- [x] 4.1 `partials/run_chain.html`: full chain from any run, with comment, decision and rationale
- [x] 4.2 `partials/run_continue.html`: "Continue this run" form on run detail

## 5. Tests & docs

- [x] 5.1 Unit tests: context building and caps, prompt, loader degradation, process and queue properties, web view (400/404/now/queue), chain from the original and from a continuation, partials, API
- [x] 5.2 Update `specs/zebra-as-is.md`
