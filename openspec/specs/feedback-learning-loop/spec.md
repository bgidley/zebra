### Requirement: MemoryStore exposes workflow memory lookup by run ID
The `MemoryStore` interface SHALL provide a `get_workflow_memory_by_run_id(run_id: str)`
method that returns the `WorkflowMemoryEntry` for a given run, or `None` if not found.
All concrete implementations (InMemoryMemoryStore, DjangoMemoryStore) MUST implement it.

#### Scenario: Entry exists for run
- **WHEN** `get_workflow_memory_by_run_id` is called with a `run_id` that matches a stored entry
- **THEN** the matching `WorkflowMemoryEntry` is returned

#### Scenario: Entry does not exist
- **WHEN** `get_workflow_memory_by_run_id` is called with an unknown `run_id`
- **THEN** `None` is returned

### Requirement: UpdateConceptualMemoryAction includes user feedback in LLM prompt
When `UpdateConceptualMemoryAction` runs, it SHALL include any non-empty `user_feedback`
values from the most recent `WorkflowMemoryEntry` records in the LLM prompt so the
conceptual index reflects user corrections.

#### Scenario: Recent memories contain user feedback
- **WHEN** one or more of the recent `wf_memories` records have a non-empty `user_feedback` field
- **THEN** those feedback strings are included in the LLM prompt sent to update conceptual memory

#### Scenario: No user feedback present
- **WHEN** all recent `wf_memories` records have empty `user_feedback`
- **THEN** the prompt is unchanged from the current behaviour (no feedback section added)

### Requirement: Feedback submission triggers conceptual memory refresh
After a user submits free-text feedback via `AgentLoop.record_feedback()`, the system SHALL
asynchronously re-run the conceptual memory update for the workflow associated with that run,
incorporating the new feedback text.

#### Scenario: Feedback submitted for a known run
- **WHEN** `record_feedback(run_id, feedback)` is called and the run's memory entry is found
- **THEN** `user_feedback` is persisted to the memory store AND a conceptual memory refresh is scheduled asynchronously

#### Scenario: Feedback submitted for an unknown run
- **WHEN** `record_feedback(run_id, feedback)` is called and no matching memory entry exists
- **THEN** `False` is returned and no refresh is triggered (existing behaviour preserved)

#### Scenario: Refresh fails gracefully
- **WHEN** the conceptual memory refresh LLM call raises an exception
- **THEN** the exception is logged and swallowed; the web response is unaffected and `record_feedback` still returns `True`

### Requirement: Conceptual memory refresh does not block the web response
The post-feedback conceptual memory refresh SHALL be fire-and-forget (e.g. via
`asyncio.create_task`) so the HTTP response to the user is returned before the LLM
call completes.

#### Scenario: User submits feedback
- **WHEN** the feedback form is submitted
- **THEN** the HTTP response is returned promptly and the conceptual memory update runs in the background
