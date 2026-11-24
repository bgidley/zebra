## Context

`zebra-tasks/zebra_tasks/agent/analyzer.py` builds `workflow_stats` (`_workflow_stats`) and `low/high_performers` (fixed thresholds 0.7/0.9 with `total_runs >= min_runs`). `evaluator.py` (~l.377-410) renders them into the LLM prompt as `N runs, X% success`.

## Decisions

- **Wilson score interval, z=1.96**: sound for small n and for 0%/100% rates, no dependencies. Helper `wilson_interval(successes, n) -> tuple[float, float] | None` (None when n=0) in `zebra_agent/metrics.py`, JSON-safe floats.
- **Confidence label** from `total_runs`: 0 → `none`, `< min_runs_for_analysis` (default 3) → `insufficient`, else `adequate`. Keys added to each stat: `success_ci_low`, `success_ci_high`, `confidence`. `success_rate` stays for compatibility (None is not introduced; zero-run entries omit it by carrying `success_rate: None`, and consumers that sort on it use `.get(..., 0)` already).
- **Zero-run workflows**: `_workflow_stats` currently skips them. Emit them with `total_runs: 0`, `successful_runs: 0`, `confidence: none`, no interval. Sorted last. `unique_workflows` keeps counting only workflows that ran, so a new `workflows_without_runs` count is added instead.
- **Categorisation**: `low_performers`: keep the existing point-rate rule (rate < 0.7) and `adequate` requirement, so a failing workflow still surfaces. `high_performers`: `adequate` and CI lower bound >= 0.7 AND rate >= 0.9. 3/3 (lower 0.44) is excluded; 40/40 (lower 0.91) included.
- **Prompt**: per workflow `name: s/n successes (rate%, 95% CI lo-hi%) [insufficient data]`; system prompt adds: do not rate health of `none`/`insufficient` workflows, name sample sizes in the summary, and say "insufficient evidence" instead of "performing well". Tool stats use the same helper over judged calls.

## Risks

- Prompt wording only nudges the LLM; the structural data is what is tested. Health score semantics unchanged.
- Callers reading `success_rate` of a zero-run entry could hit None; checked in tasks.
