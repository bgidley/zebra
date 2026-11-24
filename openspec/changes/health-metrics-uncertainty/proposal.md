## Why

The dream cycle's health report (#328) called all workflows healthy from 16 goal runs across three workflows in seven days, with no confidence bounds. `MetricsAnalyzerAction` emits a bare `success_rate`, and the evaluator prompt prints `N runs, X% success`, so the LLM cannot tell 3/3 from 300/300 and workflows with no runs vanish from the report.

## What Changes

- `MetricsAnalyzerAction` adds to every per-workflow stat: `successful_runs` alongside `total_runs` (already present), a 95% Wilson score interval (`success_ci_low`, `success_ci_high`) and a `confidence` label: `none` (no eligible runs), `insufficient` (below `min_runs_for_analysis`), `adequate`.
- Workflows known to the store with zero goal runs in the window are listed with `confidence: none` and no rate, rather than omitted. Zero-run is distinct from insufficient data.
- The evaluator prompt prints `successes/runs (rate, 95% CI low-high)` and a data-sufficiency tag per workflow, and instructs the model not to judge health for `none`/`insufficient` workflows and to state the sample size when summarising.
- High-performer categorisation also requires the interval's lower bound to be at least 0.7, so a tiny sample cannot make a workflow "high performing".
- The pure statistics helper lives in `zebra-agent` metrics code and is reused by the tool-workflow stats (#256).

## Non-goals

- Changing what counts as an eligible run (goal vs tool vs system kinds stay as in #256).
- UI changes beyond the report text; changing `WorkflowStats.success_rate` used elsewhere.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | Every per-workflow stat in the metrics analysis carries successes, eligible runs and a 95% Wilson interval | Unit tests with known values (e.g. 3/3 gives about 0.44-1.0; 0/0 gives no interval) |
| O2 | Workflows with no runs are reported as `none`, distinct from `insufficient` (under the minimum) and `adequate` | Unit test over a store with a zero-run, a 2-run and a 20-run workflow |
| O3 | A small perfect sample is no longer a "high performer"; categorisation uses the interval | Unit test: 3/3 not in `high_performers`, 40/40 is |
| O4 | The evaluator prompt shows `successes/runs`, the interval and the sufficiency tag, and tells the model not to assess thin-data workflows | Prompt-building test asserting the text; next dream-cycle report cites sample sizes in prod log |
| O5 | Existing consumers (`success_rate`, `low_performers`, tool stats) keep working | Existing analyzer/evaluator tests pass unchanged |
