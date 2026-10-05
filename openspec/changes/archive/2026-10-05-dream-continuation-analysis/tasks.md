> Branch: `f136/dream-continuations`. Reference `#136` in commits.

## 1. Implementation

- [x] 1.1 Analyzer: gather chains (leaves → `get_run_chain`, `get_task_executions`)
- [x] 1.2 Analyzer: per-workflow `continued_runs` / `continuation_rate`
- [x] 1.3 Analyzer: frequently continued, capability gaps, added steps, proposals; graceful degradation
- [x] 1.4 Evaluator: continuation section in prompt; merge proposals into `improvement_priorities`
- [x] 1.5 Optimizer: `source` on changes, `continuation_changes` output
- [x] 1.6 `dream_cycle.yaml` v4: "Continuations" summary section

## 2. Tests & docs

- [x] 2.1 Tests with seeded chains in `InMemoryMetricsStore` (analyzer, evaluator merge, optimizer, no continuations, store failure)
- [x] 2.2 Dream cycle definition test for the Continuations section
- [x] 2.3 F136 bullet in `specs/zebra-as-is.md`
