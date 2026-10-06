## ADDED Requirements

### Requirement: Stores report continued runs per workflow
The metrics stores SHALL report, for each workflow, `continued_runs` — the number of that workflow's runs that at least one other run continues (its `extends_run_id` references the run) — and `WorkflowStats.continuation_rate` SHALL equal `continued_runs / total_runs`, or 0 when there are no runs.

#### Scenario: Run continued twice counts once
- **WHEN** a workflow has 4 runs and one of them is continued by two later runs
- **THEN** `get_stats` reports `continued_runs` = 1 and `continuation_rate` = 0.25

#### Scenario: Workflow without continuations
- **WHEN** no run of a workflow is referenced by any `extends_run_id`
- **THEN** `continued_runs` is 0 and `continuation_rate` is 0

### Requirement: Web UI shows continuation rate beside success rate
The workflow detail page SHALL show a "Continued" stat with the rate and "X of N runs", and the dashboard top-workflows list and the workflow library list SHALL show "N% continued" next to success rate for workflows that have continued runs.

#### Scenario: Library list row with continuations
- **WHEN** a workflow has continued runs
- **THEN** its row shows its success rate followed by "N% continued"

#### Scenario: Library list row without continuations
- **WHEN** a workflow has no continued runs
- **THEN** its list row shows only the success rate

### Requirement: API exposes continuation rate
Workflow stats returned by the API SHALL include `continued_runs` and `continuation_rate`.

#### Scenario: Stats endpoint
- **WHEN** a client requests a workflow's stats
- **THEN** the response includes `continued_runs` and `continuation_rate` alongside `success_rate`
