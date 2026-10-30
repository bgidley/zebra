# dream-metrics-classification Specification

## Purpose
TBD - created by archiving change dream-metrics-classification. Update Purpose after archive.

## Requirements
### Requirement: The dream metrics analysis tells goal, tool and system runs apart
`metrics_analyzer` SHALL classify each run in the analysis period as a tool run when its goal
starts with the `llm_agent` tool-goal prefix, else as a system run when its workflow is tagged
`system` in the workflow library, else as a goal run. Per-workflow statistics, low and high
performers, the unrated-run count, failure patterns, usage trends and recommendations SHALL be
built from goal runs only. The analysis SHALL report `run_counts` with the number of goal, tool
and system runs and of expected misses, and `system_workflow_stats` for system runs.

#### Scenario: Tool runs do not inflate goal statistics
- **WHEN** the period has 2 goal runs of *Research* (one failed) and 10 successful tool runs of
  *Read Zebra Source*
- **THEN** `workflow_stats` lists only *Research* with 2 runs and 50% success, and `run_counts`
  is `goal: 2, tool: 10, system: 0`, summing to the 12 runs analysed

#### Scenario: System workflows are counted apart
- **WHEN** the library tags *Outcome Review* `system` and the period has a failed run of it
- **THEN** it appears in `system_workflow_stats` and `run_counts.system`, and not in
  `workflow_stats`, `low_performers` or `failure_patterns`

#### Scenario: No library
- **WHEN** no workflow library is available
- **THEN** no run is classed as system and the analysis still succeeds

### Requirement: Tool workflows are reported with expected misses apart from failures
The analysis SHALL report `tool_workflow_stats`, one entry per tool workflow with its calls,
successes, expected misses, real failures and a success rate over the calls that were not
expected misses (`None` when all were), and `tool_failure_patterns` built from real tool
failures only. A failed tool run SHALL be an expected miss when `zebra_source.is_expected_miss`
holds for its error.

#### Scenario: Misses are not failures
- **WHEN** *List Zebra Source* has 6 calls: 3 succeeded, 2 failed with "'x' does not exist." and 1
  failed with a crash
- **THEN** its entry has `expected_misses: 2`, `failures: 1`, success rate 0.75, and
  `tool_failure_patterns` holds only the crash

### Requirement: Expected misses are recognised from zebra_source's own messages
`zebra_source.is_expected_miss(error)` SHALL be true for the messages `zebra_source` returns when
a path does not exist, is not deployed, is a directory given to `read` or a file given to `list`,
and false for refusals (hidden or secret files, paths outside the tree, non-source entries),
invalid input and any other error.

#### Scenario: Real messages
- **WHEN** `ZebraSourceAction` fails on a missing path, an undeployed top-level entry, a directory
  to read and a file to list
- **THEN** `is_expected_miss` is true for each of its errors

#### Scenario: Refusals, crashes and unknown errors
- **WHEN** it refuses a `.env` file, a path outside the tree or an invalid regex, or the error
  is a crash, empty, or any other text
- **THEN** `is_expected_miss` is false and the run counts as a failure

### Requirement: The dream evaluator sees the split
The workflow evaluator's prompt SHALL give the goal, tool and system run counts, label workflow
statistics as goal runs, and list tool workflows in their own section with expected misses
apart from real failures. Expected misses SHALL NOT appear under failure patterns. The leak
guard's run texts SHALL include the tool failure patterns.

#### Scenario: Prompt sections
- **WHEN** the analysis has goal stats and a tool workflow with misses and one real failure
- **THEN** the prompt has a tool section naming the misses and the failure, and the miss text is
  not in it

#### Scenario: Leak guard
- **WHEN** a tool failure pattern holds a sample goal
- **THEN** the leak guard's run texts include that goal
