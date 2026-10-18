## ADDED Requirements

### Requirement: Golden tasks are curated files
Golden tasks SHALL be YAML files in the golden directory (`zebra-agent/golden/`, overridable by
`ZEBRA_GOLDEN_TASKS_DIR`), each with an `id`, the `workflow` name it exercises, a `goal`, an
`expected` outcome and a non-empty list of `criteria`. `WorkflowLibrary.list_golden_tasks()`
SHALL return the valid ones and skip invalid files with a warning.

#### Scenario: Valid golden task
- **WHEN** the golden directory holds a file with id, workflow, goal, expected and criteria
- **THEN** `list_golden_tasks()` returns it

#### Scenario: Invalid file
- **WHEN** a golden file is unparseable or has no criteria
- **THEN** it is skipped and the other golden tasks are still returned

### Requirement: The gym scores workflow outputs against golden criteria
`run_golden_gym` SHALL run each selected golden task's workflow as a child process with the
golden goal, suspend until the children finish, and have an LLM judge score each output against
the task's criteria from 0 to 1. A failed run SHALL score 0. Every score SHALL be recorded as a
`GymScore` in the `MetricsStore`.

#### Scenario: On-demand run
- **WHEN** the *Golden Gym* workflow runs with no candidates
- **THEN** the current version of every workflow with golden tasks is run on them and one score per golden task is recorded

#### Scenario: Workflow run fails
- **WHEN** a golden task's workflow run fails
- **THEN** that task scores 0 with the error recorded

### Requirement: Self-modified workflows are promoted only if they do not regress
When the Dream Cycle optimizer runs with `gym_gate: true`, it SHALL stage each workflow
modification instead of saving it. The gym SHALL run the current version and the candidate on the
workflow's golden tasks and save the candidate only if its mean score is not more than `tolerance`
below the current version's. A rejected candidate SHALL NOT be saved and SHALL be reported in
`optimization_results.failed_changes` with both scores.

#### Scenario: Degraded candidate
- **WHEN** a staged modification scores below the current version by more than the tolerance
- **THEN** it is not saved and appears in `failed_changes` with reason `gym regression`

#### Scenario: Candidate as good or better
- **WHEN** a staged modification scores within the tolerance of the current version or higher
- **THEN** it is saved and listed in `changes_made` and `modified_workflows`

#### Scenario: No golden tasks
- **WHEN** a staged modification's workflow has no golden tasks
- **THEN** it is saved as before and marked `ungated`

### Requirement: The gate fails closed and never fails the cycle
A gated candidate the gym cannot run safely (a manual task, an unregistered or
`always_irreversible` action) or cannot score (no LLM provider, unparseable judge reply) SHALL be
rejected. Gym errors SHALL NOT fail the Dream Cycle.

#### Scenario: Candidate adds a human task
- **WHEN** a staged candidate with golden tasks contains an `auto: false` task
- **THEN** it is rejected without being run

#### Scenario: No LLM provider
- **WHEN** the judge has no LLM provider
- **THEN** every gated candidate is rejected, ungated ones are still saved, and the cycle continues

### Requirement: Gym scores are visible over time
The `/gym/` page SHALL list each golden task with its latest score for the current version, its
recent score history, and recent gate decisions (promoted or rejected, with both scores).

#### Scenario: After gym runs
- **WHEN** scores have been recorded
- **THEN** `/gym/` shows each golden task's latest score and history, and each gate decision
