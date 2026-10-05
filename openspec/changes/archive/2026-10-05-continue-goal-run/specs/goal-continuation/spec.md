## ADDED Requirements

### Requirement: Continue a finished run with a progress comment

The system SHALL let a user continue one of their own finished runs, successful or failed, by providing a comment on where the run got to and what should happen next. The web run detail page SHALL offer a "Continue this run" form with two options: run now, or queue for the budget daemon. The API SHALL expose `POST /api/runs/<run_id>/continue/`, which queues the continuation and returns 202 with the new process ID and run ID. The continuation SHALL keep the previous run's goal text, and SHALL store the comment as the `continuation_comment` process property alongside `previous_run_context`.

#### Scenario: Continue a failed run now

- **WHEN** the user submits a comment on the run page of one of their failed runs and chooses "Continue now"
- **THEN** a new run starts with the previous run's goal, the `previous_run_context` of the failed run, and `continuation_comment` set to the comment

#### Scenario: Queue a continuation via the API

- **WHEN** a client posts `{"comment": "..."}` to `/api/runs/<id>/continue/` for a finished run
- **THEN** a CREATED Agent Main Loop process is queued carrying `previous_run_context` and `continuation_comment`, and the response is 202 with `process_id`, `run_id` and `continues_run_id`

#### Scenario: Comment is required and the run must be the user's and finished

- **WHEN** the comment is blank, the run belongs to another user, or the run is still in progress
- **THEN** no continuation is created, and the response is 400 for a blank comment or 404 otherwise

### Requirement: Continuation context includes progress, the comment and the chain

When a run is continued or followed up, `previous_run_context` SHALL include task-level progress for that run: task name, state, and a truncated output or error, for up to 20 tasks. When the run has predecessors, it SHALL include a compact summary of the earlier runs in its chain: at most the last 5 runs, each with goal, workflow, outcome and comment, never nesting their full contexts. The annotated goal seen by reasoning steps SHALL lead with the user's continuation comment when present.

#### Scenario: Continuation prompt shows where it got to

- **WHEN** a run whose second task failed is continued with a comment
- **THEN** the annotated goal contains the comment, each task with its state (including the failure's error), and the previous outcome as failed

#### Scenario: Context loading degrades gracefully

- **WHEN** task executions or the chain cannot be loaded from the metrics store
- **THEN** the continuation proceeds with the basic previous-run context

### Requirement: Run chains are persisted and visible

Each continuation run SHALL record `extends_run_id` and its `continuation_comment` in the metrics store, so the chain survives restarts. `MetricsStore.get_run_chain(run_id)` SHALL return the chain from the root to the run, oldest first. The run detail page SHALL show the whole chain (original, then continuation 1, 2, …) when viewed from any run in it, including continuations started after the viewed run, with each continuation's comment and, when present, its decision and rationale.

#### Scenario: Chain visible from the original run

- **WHEN** the user opens the original run of a chain with two continuations
- **THEN** the page lists the original, continuation 1 and continuation 2 in order, with links and comments

#### Scenario: Standalone run shows no chain

- **WHEN** a run has no predecessor and no continuations
- **THEN** no chain section is rendered
