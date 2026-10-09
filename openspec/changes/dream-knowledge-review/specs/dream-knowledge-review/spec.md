## ADDED Requirements

### Requirement: Dream cycle reviews knowledge of users with recent runs
The Dream Cycle SHALL run a `review_knowledge` step after workflow optimisation that, for each user owning at least one workflow run since the previous completed dream cycle (or the last `lookback_days` when there is none), gathers the user's active knowledge entries and recent runs (goal, outcome, rating, continuation comment, answers to the workflow's human tasks) and asks an LLM for `new`, `update`, `stale`, `merge` and `reinforce` proposals. Users without runs in the window, and runs without an owner, SHALL NOT cause an LLM call.

#### Scenario: Idle user skipped cheaply
- **WHEN** a user has knowledge entries but no runs since the cutoff
- **THEN** no LLM call is made for that user and their entries are unchanged

#### Scenario: Window starts at the previous dream cycle
- **WHEN** a previous Dream Cycle process completed after some runs started
- **THEN** those earlier runs are not reviewed again

#### Scenario: Run owner recorded
- **WHEN** `assess_and_record` records a run of a process with `__user_id__`
- **THEN** the recorded `WorkflowRun.user_id` is that user, and the Django store persists and returns it

### Requirement: Agent entries change directly, human entries only through proposals
The review SHALL apply proposals by source. Agent-sourced entries MAY be updated, have confidence lowered, be reinforced or be soft-deleted as duplicates. New facts SHALL follow `add_knowledge` semantics with `source="agent"` and confidence below 1.0. Entries with `source="human"` SHALL NOT be written: a conflicting value SHALL start the *Resolve Knowledge Contradiction* workflow and stale or duplicate human entries SHALL start *Knowledge Verification* for exactly those entries. Stale entries SHALL NOT be deleted.

#### Scenario: Missing fact added
- **WHEN** the LLM proposes a new fact whose key is not stored
- **THEN** an entry is created with `source="agent"` and confidence below 1.0

#### Scenario: Contradicted human entry
- **WHEN** the LLM proposes a different value for a human entry
- **THEN** the entry is unchanged and a *Resolve Knowledge Contradiction* process waits on the user with the existing and proposed values

#### Scenario: Stale time-sensitive agent entry
- **WHEN** the LLM flags an agent entry as stale
- **THEN** its confidence is lowered below the verification threshold and it is not deleted

#### Scenario: Stale human entry
- **WHEN** the LLM flags a human entry as stale
- **THEN** the entry is unchanged and a *Knowledge Verification* process is started for exactly that entry

#### Scenario: Proposal already pending
- **WHEN** an unfinished contradiction proposal exists for the same entry and value
- **THEN** no second proposal is started

### Requirement: Knowledge review is auditable and reported
The review SHALL record every direct change and proposal with the entry's state before and after, keep the record on the dream-cycle process, provide a way to revert the direct changes, and never fail the dream cycle. The dream cycle summary SHALL include a "Knowledge" section with counts of added, updated, stale-flagged, merged and reinforced entries and examples.

#### Scenario: Revert
- **WHEN** `revert_knowledge_changes` is applied to a review's changes
- **THEN** updated entries regain their previous value and confidence, merged duplicates are restored and added entries are soft-deleted

#### Scenario: Unusable LLM reply
- **WHEN** the LLM reply is not valid JSON
- **THEN** nothing changes, an error is reported and the step succeeds

#### Scenario: Summary section
- **WHEN** the dream cycle summary is generated
- **THEN** its prompt includes a "Knowledge" section fed by `knowledge_review.counts` and `knowledge_review.examples`
