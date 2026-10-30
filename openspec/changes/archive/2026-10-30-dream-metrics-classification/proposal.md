## Why

The dream cycle judges Zebra's workflows from `metrics_analyzer`, which puts every recorded run in
one pot. Tool runs (*Search/Read/List Zebra Source* called by `llm_agent`, recorded with a
`[tool] ` goal, #146) outnumber goal runs and inflate run counts and success rates. Their expected
misses, such as a path that does not exist or is not deployed, count as hard failures. The
evaluator then proposes fixes for "failures" that were correct answers (#255, #257 and #258 came
from this), and goal-level effectiveness cannot be read from the analysis. Closes #256.

## What Changes

- `metrics_analyzer` classifies each run as **goal**, **tool** (goal starts with the
  `llm_agent` tool prefix) or **system** (workflow tagged `system` in the library, when the
  library is available).
- Goal runs alone feed `workflow_stats`, `low_performers`, `high_performers`,
  `unrated_runs_count`, `failure_patterns`, `usage_trends` and the recommendations.
- New `run_counts` (`goal`, `tool`, `system`, `expected_misses`), `tool_workflow_stats` (per tool
  workflow: calls, successes, expected misses, real failures, success rate over calls that were
  not expected misses), `tool_failure_patterns` (real tool failures only) and
  `system_workflow_stats`.
- `zebra_source` gains `is_expected_miss(error)`, matching its own not-found, not-deployed and
  wrong-kind messages (directory given to `read`, file given to `list`). Refusals are not misses.
- The evaluator prompt shows goal statistics, then a tool section that lists expected misses
  apart from real failures. The leak guard's run texts include the tool failure patterns.

## Capabilities

### New Capabilities
- `dream-metrics-classification`: the dream cycle's metrics analysis tells goal, tool and system
  runs apart and counts expected tool misses apart from failures.

### Modified Capabilities
<!-- None -->

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | Goal-workflow statistics in the dream analysis come from goal runs only; tool and system runs are counted, not mixed in | Unit tests with mixed goal / tool / system runs: `workflow_stats`, performers, failure patterns, unrated count and usage trends hold only goal runs; `run_counts` goal + tool + system equals all runs analysed (no double count). Confirmation only: the next prod dream cycle's `metrics_analysis` has `run_counts` |
| O2 | Tool workflows are reported on their own, with expected misses apart from real failures | Unit tests: `tool_workflow_stats` counts calls, successes, expected misses and failures; success rate = successes / (calls − misses), `None` when every call was a miss; `tool_failure_patterns` holds real failures only. A tool error that matches no miss message (including older records) stays a failure |
| O3 | An expected miss is recognised from the exact message `zebra_source` returns; a refusal, crash or unknown error is not | Tests run `ZebraSourceAction` on missing, not-deployed, directory-as-file and file-as-directory paths and feed its real error to `is_expected_miss` (true); secret, outside-tree and bad-regex refusals, a crash message, an empty error and an unrelated error give false |
| O4 | The dream evaluator sees the split, never shows an expected miss as a failure pattern, and tool failure text gets the existing leak protection | Unit tests on the evaluator prompt: run counts, goal statistics, tool section with misses and real failures, no miss text under Failure Patterns; the leak guard's run texts include tool failure patterns |

## Non-goals

- The curator's failing rule (it reads store-wide `get_all_stats`) and the web dashboard's
  success rates: follow-up issue.
- Collecting ratings (#214) or changing what `zebra_source` returns for a miss (#255).

## Impact

- `zebra-tasks/zebra_tasks/agent/analyzer.py`, `evaluator.py`, `leak_guard.py`,
  `agent/zebra_source.py`, `llm/agent.py` (named tool-goal prefix).
- Analysis output only gains keys; existing keys keep their shape.
