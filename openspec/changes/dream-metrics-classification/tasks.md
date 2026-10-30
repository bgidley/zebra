> Branch: `f256/tool-metrics`. Reference `#256` in commits (`Closes #256` on the last).

## 1. Classification

- [x] 1.1 `llm/agent.py`: named `TOOL_GOAL_PREFIX`, used when recording tool runs
- [x] 1.2 `zebra_source.py`: `EXPECTED_MISS_MARKERS`, `is_expected_miss(error)`
- [x] 1.3 `analyzer.py`: classify goal / tool / system; goal-only stats; `run_counts`,
      `tool_workflow_stats`, `tool_failure_patterns`, `system_workflow_stats`

## 2. Consumers

- [x] 2.1 `evaluator.py`: run counts, goal-run label, tool section, tool failure patterns
- [x] 2.2 `leak_guard.py`: `run_texts_from_metrics` includes tool failure patterns

## 3. Tests and docs

- [x] 3.1 Tests: analyzer split, tool misses, system tag, no library; `is_expected_miss` against
      real action errors; evaluator prompt; leak guard
- [x] 3.2 `zebra-tasks/AGENTS.md`, `specs/zebra-as-is.md`
- [x] 3.3 Follow-up issue #260: curator failing rule and dashboard read store-wide stats with misses
