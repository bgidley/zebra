## Context

`MetricsAnalyzerAction` (`metrics_analyzer`, first step of *Dream Cycle*) reads `get_runs_since`
and builds one set of per-workflow statistics. `llm_agent` records each tool call as a
`WorkflowRun` with cost 0 and goal `[tool] <arguments>` (#146), so tool workflows dominate the
counts. A failed tool run's `error` is the failing task's message verbatim (the engine copies it
to `__error__`, then into `subflow_results`), so `zebra_source`'s own messages reach the metrics
unchanged.

## Decisions

- **Classify by data already recorded.** Tool: goal starts with `TOOL_GOAL_PREFIX`
  (`zebra_tasks.llm.agent`, now a named constant used for writing and reading). System: workflow
  name tagged `system` in `__workflow_library__`; without a library nothing is system. No new
  column or migration.
- **Expected misses live next to the messages.** `zebra_source.is_expected_miss(error)` matches
  `EXPECTED_MISS_MARKERS`, phrases taken from the messages `missing_path_message`, `_read` and
  `_list` build. Tests drive the real action to produce each message, so a reworded message
  breaks a test rather than silently turning misses back into failures. Only tool runs are
  checked: a goal run that fails is a real failure whatever its text.
- **Tool success rate excludes misses**: `successful / (total - expected_misses)`, `None` when
  every call was a miss. A miss is a correct answer, not a success or failure of the tool.
- **System runs** get the same per-workflow shape as goal runs (`system_workflow_stats`) but stay
  out of performers, failure patterns and recommendations, so the cycle does not try to "improve"
  its own plumbing from them.
- **Keep the old keys.** `total_runs_analyzed` stays all runs; `unique_workflows` counts goal
  workflows. Consumers that ignore the new keys see goal-only numbers, which is the fix.

## Risks / Trade-offs

- A tool run recorded before the prefix existed would count as a goal run; #146 added both
  together, so none exist.
- The curator still reads store-wide stats including misses (follow-up issue).
