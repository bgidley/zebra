# goal-continuation Specification

## Purpose
Let a user continue a finished (successful or failed) goal run by commenting on where it got to; the continuation carries the run's task progress and a flat chain summary, and run lineage is persisted so chains are visible and analysable (F134, #134).

## Requirements

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

### Requirement: Retrying a failed run resumes where it stopped

When the continuation assessor chooses `same_workflow` for a previous run that failed in that
same workflow, `execute_goal_workflow` SHALL start the new goal-workflow process at the tasks the
failed process never completed, with the failed process's workflow properties and completed task
outputs carried over, so answered human tasks are not asked again. The new process SHALL record
`__resumed_from__` with the failed process id and the start task ids. In every other case the
workflow SHALL start at its first task.

#### Scenario: Retry after the last step failed

- **WHEN** a run's goal workflow failed on an auto task after the user answered its forms, and the user continues it with "Retry" and the assessor chooses `same_workflow`
- **THEN** the new goal workflow starts at the failed task, no form is asked again, completed tasks are not re-run, and the answers are available to the resumed task

#### Scenario: Previous run succeeded or another workflow chosen

- **WHEN** the previous run succeeded, or the assessor chooses `existing_workflow` or `new_workflow`
- **THEN** the goal workflow starts at its first task

#### Scenario: Workflow changed since the failure

- **WHEN** a task the failed process had not completed no longer exists in the workflow definition, or is a synchronized join
- **THEN** the goal workflow starts at its first task

#### Scenario: Retry of a retry

- **WHEN** a resumed run fails again and is retried
- **THEN** the new goal workflow resumes from the latest failed attempt

### Requirement: Processes can start at given tasks

`WorkflowEngine.start_process` and `start_process_with_timeout` SHALL accept optional
`start_task_ids`. When given, the process SHALL start with one task per id, each on its own flow
of execution, instead of the definition's first task; an unknown id SHALL raise.

#### Scenario: Start at a later task

- **WHEN** a process is started with `start_task_ids` naming its second auto task
- **THEN** only that task and its successors run

### Requirement: Continuations expose the previous run's outputs
When `execute_goal_workflow` starts the goal workflow for a goal whose `previous_run_context` names a run, it SHALL look up that run's goal-workflow process (completed or failed) and SHALL pass its workflow properties to the new child process as the `prior_outputs` dict. It SHALL leave out keys starting with `__`, `goal` and `prior_outputs`. A string value longer than 8000 characters SHALL be cut to 8000; any other value whose JSON is longer than 8000 characters SHALL be dropped; a value that would take the dict's total size past 32000 characters SHALL be left out. When the previous process cannot be found, the goal workflow SHALL start without `prior_outputs` and a warning SHALL be logged.

#### Scenario: Prior output reachable from a template
- **WHEN** a goal continues run *A*, whose goal workflow set `research_brief`, and the new workflow's task prompt is `{{prior_outputs.research_brief}}`
- **THEN** the task's prompt resolves to *A*'s research brief

#### Scenario: Not a continuation
- **WHEN** a goal has no `previous_run_context`
- **THEN** the goal workflow has no `prior_outputs` property

#### Scenario: Internal and oversized values left out
- **WHEN** the previous goal workflow has `__task_output_x`, `goal`, `prior_outputs`, a 20000-character string and a list whose JSON is 20000 characters
- **THEN** `prior_outputs` has none of the first three, the string is cut to 8000 characters and the list is absent

#### Scenario: Previous process missing
- **WHEN** a goal's `previous_run_context` names a run with no stored process
- **THEN** the goal workflow starts without `prior_outputs` and a warning is logged

### Requirement: Inputs bind to prior outputs with from_prior
An input in a workflow's `inputs` schema MAY declare `from_prior: <key>`. When the goal workflow starts with `prior_outputs` containing `<key>`, the input SHALL be set to that value, unless the child's properties already set it. Without `prior_outputs`, or without that key, the input SHALL be left unset.

#### Scenario: Input bound from the previous run
- **WHEN** a continuation runs a workflow declaring `prior_brief: {type: string, from_prior: research_brief}` and the previous run set `research_brief`
- **THEN** the child's `prior_brief` property is the previous research brief

#### Scenario: Key missing in the previous run
- **WHEN** the previous run did not set `research_brief`
- **THEN** the child has no `prior_brief` property

### Requirement: Workflow authors are told about prior outputs
The workflow creator's and optimizer's prompts SHALL say that on a continuation `{{prior_outputs.<key>}}` holds the previous run's value of an output key and that an input can declare `from_prior: <key>`.

#### Scenario: Prompts mention prior outputs
- **WHEN** the creator or optimizer builds its prompt
- **THEN** the prompt mentions `prior_outputs` and `from_prior`
