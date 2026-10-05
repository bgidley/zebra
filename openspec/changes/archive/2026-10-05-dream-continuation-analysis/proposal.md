## Why

A continued goal is a learning signal: the original workflow did not fully satisfy the user, and the continuation comment says why. The dream cycle currently ignores run lineage, so it cannot learn from repeated "carry on and also do X" requests or from continuations that needed a brand-new workflow. GitLab issue #136.

## What Changes

- `metrics_analyzer` gathers continuation chains in the analysis window (`get_continuations_since` + `get_run_chain` + `get_task_executions`) and adds a `continuation_analysis` block: per-chain original workflow, where it stopped, comments, assessor decisions/rationales, final outcome; frequently continued workflows; capability gaps (`new_workflow` decisions); steps added after the fact; targeted improvement proposals.
- Per-workflow `continued_runs` and `continuation_rate` (continued runs / total runs) added to `workflow_stats`, computed in the analyzer (no store contract change).
- `workflow_evaluator` shows continuation findings to the LLM and merges the continuation proposals into `improvement_priorities` so they reach the optimizer even if the LLM omits them.
- `workflow_optimizer` tags results with their source and reports `continuation_changes`; all YAML still goes through the #128 validation.
- `dream_cycle.yaml` v4: summary prompt gets a "Continuations" section.

## Capabilities

### New Capabilities
- `dream-continuation-analysis`: dream cycle analysis of continuation chains, continuation rate, and continuation-driven improvement proposals.

### Modified Capabilities
<!-- none -->

## Impact

- `zebra-tasks/zebra_tasks/agent/analyzer.py`, `evaluator.py`, `optimizer.py`
- `zebra-agent/workflows/dream_cycle.yaml`
- Tests in `zebra-tasks/tests/`, `zebra-agent/tests/test_dream_cycle_workflow.py`
- No DB migration; relies on the continuation lineage fields added for #134/#135 (may be `None`).
