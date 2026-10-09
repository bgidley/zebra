## MODIFIED Requirements

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
