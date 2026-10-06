# Spec Delta

## Purpose

Lets a Zebra workflow decide whether it needs past workflow runs, fetch them filtered by time
window and search text, and use the result in later planning and execution steps.

## ADDED Requirements

### Requirement: Filtered workflow run search
The metrics store SHALL support searching past workflow runs. Every filter is optional:
- start time (inclusive) and end time (exclusive), compared against the run's start time in UTC
- search text, matched case-insensitively against the run's goal
- workflow name (exact match)
- success flag
- a result limit

Results SHALL be ordered newest first. The limit SHALL default to 20 and SHALL be capped at 200.
When a current user is set, results SHALL include only that user's runs.

#### Scenario: Date window filter
- **WHEN** runs exist on 1 Oct, 3 Oct and 5 Oct and a search is made with start 2 Oct and end 5 Oct
- **THEN** only the 3 Oct run is returned

#### Scenario: Text filter is case-insensitive
- **WHEN** a run has the goal "Compare Pension providers" and a search is made with text "pension"
- **THEN** that run is returned

#### Scenario: Combined filters
- **WHEN** a search is made with text, a date window and success=true
- **THEN** only runs that match every filter are returned, newest first

#### Scenario: Limit is capped
- **WHEN** a search is made with limit 10000
- **THEN** at most 200 runs are returned

#### Scenario: User scoping
- **WHEN** user A searches with no other filters
- **THEN** no runs belonging to user B are returned

### Requirement: Workflow history task
The system SHALL provide a `get_workflow_history` task action. It accepts start time, end time,
search text, workflow name, success and limit as templatable properties. Times SHALL be accepted as
ISO-8601 or as a relative offset from now (for example `-7d`, `24h`, `-30m`); an unsigned offset
means that far in the past. The action SHALL output:
- `runs`: a JSON-serialisable list of compact run records (id, workflow name, goal, started at,
  success, rating, and output/error truncated to a fixed length)
- `count`
- `filters`: the resolved filters
- `history_context`: a human/LLM-readable summary whose total size is bounded

The action SHALL exclude the run it is executing within.

#### Scenario: Relative window
- **WHEN** the task runs with `since: "-7d"` and text "pension"
- **THEN** it returns runs from the last 7 days whose goal mentions "pension", and `filters` shows
  the resolved absolute start time

#### Scenario: No matches
- **WHEN** no runs match the filters
- **THEN** the task succeeds with `count` 0, an empty `runs` list, and a `history_context` stating
  that no matching history was found

#### Scenario: Store unavailable
- **WHEN** no metrics store is available to the task
- **THEN** the task succeeds with empty history and logs a warning, rather than failing

#### Scenario: Invalid time value
- **WHEN** `since` is not a valid ISO-8601 timestamp or relative offset
- **THEN** the task fails with a message naming the invalid value

#### Scenario: Output is bounded
- **WHEN** matching runs have very large outputs
- **THEN** each run's output is truncated and `history_context` does not exceed its size limit

### Requirement: History-need decision
The system SHALL provide an `assess_history_need` task action. It decides from the goal whether past
workflow history is needed, routes `needs_history` or `no_history`, and when history is needed
outputs the extracted filters (start time, end time, search text). A goal with no history or time
cues SHALL route `no_history` without calling an LLM. If the LLM call fails or returns an
unparseable answer, the action SHALL route `no_history` instead of failing the process.

#### Scenario: Goal referencing past work
- **WHEN** the goal is "what did I ask you about pensions last week?"
- **THEN** the task routes `needs_history`, with search text related to "pensions" and a start time
  about 7 days ago

#### Scenario: Ordinary goal skips LLM
- **WHEN** the goal is "write a haiku about autumn"
- **THEN** the task routes `no_history` and makes no LLM call

#### Scenario: LLM failure degrades
- **WHEN** the goal has history cues but the LLM call errors
- **THEN** the task routes `no_history` and the process continues

### Requirement: History flows into planning and execution
When the agent main loop fetches history, the workflow selector SHALL receive the history context as
planning input. The executed goal workflow SHALL receive the history context appended to its goal.
When no history was fetched, the selector input and the goal SHALL be unchanged.

#### Scenario: History reaches the executed workflow
- **WHEN** a goal routes `needs_history` and matching runs are found
- **THEN** the child workflow's goal contains the original goal followed by a delimited
  workflow-history section

#### Scenario: No history leaves goal untouched
- **WHEN** a goal routes `no_history`
- **THEN** the child workflow's goal is identical to what it would have been without this feature
