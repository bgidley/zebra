# workflow-history Specification

## Purpose
Lets a Zebra workflow decide whether it needs past workflow runs, fetch them filtered by time
window and search text, and use the result in later planning and execution steps.

## Requirements

### Requirement: Filtered workflow run search
The metrics store SHALL support searching past workflow runs. Every filter is optional:
- start time (inclusive) and end time (exclusive), compared against the run's start time in UTC
- search text, split into keywords (lowercased words of three or more characters, excluding
  common stopwords). A run matches when its goal contains any keyword, case-insensitively. When
  no keywords remain, the whole text SHALL be matched as one case-insensitive substring.
- workflow name (exact match)
- success flag
- a result limit

Results SHALL be ordered newest first. The limit SHALL default to 20 and SHALL be capped at 200.
Results SHALL be limited to an explicitly given user. When no user is given, results SHALL be
limited to the request's current user, if there is one. The history task SHALL always pass the
goal's owner, so goals run by the background daemon (which has no request user) never see other
users' runs.

#### Scenario: Date window filter
- **WHEN** runs exist on 1 Oct, 3 Oct and 5 Oct and a search is made with start 2 Oct and end 5 Oct
- **THEN** only the 3 Oct run is returned

#### Scenario: Text filter is case-insensitive
- **WHEN** a run has the goal "Compare Pension providers" and a search is made with text "pension"
- **THEN** that run is returned

#### Scenario: Multi-word text matches any keyword
- **WHEN** a run has the goal "I need to plan a holiday to Scotland" and a search is made with text
  "holiday plans"
- **THEN** that run is returned

#### Scenario: Stopword-only text falls back to the whole string
- **WHEN** a search is made with text "to"
- **THEN** only runs whose goal contains "to" are returned

#### Scenario: Combined filters
- **WHEN** a search is made with text, a date window and success=true
- **THEN** only runs that match every filter are returned, newest first

#### Scenario: Limit is capped
- **WHEN** a search is made with limit 10000
- **THEN** at most 200 runs are returned

#### Scenario: User scoping
- **WHEN** user A searches with no other filters
- **THEN** no runs belonging to user B are returned

#### Scenario: Explicit user scoping without a request user
- **WHEN** the daemon (no request user) searches with user A's id
- **THEN** only user A's runs are returned

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
The system SHALL provide an `assess_history_need` task action. It decides whether past workflow
history is needed, routes `needs_history` or `no_history`, and when history is needed outputs the
extracted filters (start time, end time, search text). The decision SHALL consider the goal, the
continuation comment and the previous run's goal when those are present. A goal that is not a
continuation and has no history or time cues SHALL route `no_history` without calling an LLM. A
continuation goal (one with previous run context) SHALL always get an LLM decision. If the LLM call
fails or returns an unparseable answer, the action SHALL route `no_history` instead of failing the
process.

#### Scenario: Goal referencing past work
- **WHEN** the goal is "what did I ask you about pensions last week?"
- **THEN** the task routes `needs_history`, with search text related to "pensions" and a start time
  about 7 days ago

#### Scenario: Continuation with a history comment
- **WHEN** the goal "Our holiday plans continue - what next" continues a previous run with the
  comment "Check workflow history"
- **THEN** the LLM is asked, its prompt includes the comment, and the task routes `needs_history`
  when the LLM says so

#### Scenario: Continuation phrasing is a cue
- **WHEN** a non-continuation goal is "our holiday plans continue - what next"
- **THEN** the cue check passes and the LLM is asked

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
