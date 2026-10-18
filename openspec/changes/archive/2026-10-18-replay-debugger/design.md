## Context

The step journal (#184) appends a `ProcessEvent` per lifecycle step with the process-property
diff since the previous event. Folding the events of one task instance, excluding its first
event (whose diff holds changes made before the task began), gives exactly what that task did
to its process. That is what a replay serves.

## Decisions

**Recording = the journal.** No new table. `ProcessEvent.next_route` (nullable) is written on
`task_completed` / `task_failed` from `task.result`. `MAX_JOURNAL_VALUE_CHARS` rises from 16,000
to 256,000. A diff holds only changed values, so a large value is stored once per change, not
per step. Events from before this change have no route. `replay.recorded_steps` infers it as the
named routing whose destination step the original started next, which reproduces the path the
original took.

**Recorded step** (`zebra/core/replay.py`, `RecordedStep`): per task instance, in order of its
first event, with a terminal (`task_completed` / `task_failed`) event: `task_definition_id`,
`success`, `error`, `next_route`, folded `changed` / `removed`, and `output` (the
`__task_output_<id>` value in the state after the terminal event). Instances without a terminal
event (interrupted) are skipped. Occurrence `n` of a step in the replay is served from the `n`th
recorded instance of the same step. The counter lives in the replay's properties, so a restarted
engine resumes correctly.

**Replay marker.** The `__replay__` process property holds `{of, live, continue_live, served}`. Its presence
is the only switch. The engine checks it in `_run_task` (serve instead of running the action) and
through `_runs_itself(task_def, process)`, which is true for auto tasks and for any
recorded, non-live task while replaying. That makes manual tasks run inline at `start_process`,
in `_transition_locked`'s stack, and in `_transition_task_internal`.

**Serving** applies `removed`, then `changed`, except `__total_cost__`, `__total_tokens__`
and `__token_history__`. It saves the process, bumps `served`, and returns
`TaskResult(success, output, next_route, error)`. The engine then stores the output and routes as
usual, so routing, joins and process completion or failure behave as they would live. A
recorded step that suspended on subflows is served as its final result (no children). If a step
has no recording for that occurrence, or its recording contains an `__journal_truncated__` value,
it fails: `Replay cannot serve step 'X' (run #n): <reason>. Run it live to continue.`
With `continue_live` (opt-in), an unrecorded step runs live instead, for the steps after a
failure that a live step fixed. A human step reached that way waits for a person.

**Creating a replay** (`WorkflowEngine.create_replay`): the original must be COMPLETE or FAILED
and have a `process_started` event. Starting properties come from that event's diff, minus
`run_id` (a replay is not a run, so it stays out of activity, metrics and the daemon), plus the
marker. The definition is the original's, or a replacement. With a replacement, every step whose
`TaskDefinition` differs from the original's (or is new) joins `live`. Unknown `live` ids raise
`ReplayError`. The replay is a root process, created but not started. The caller starts it with
`start_process_with_timeout`.

**Interfaces.**
- Engine: `create_replay(process_id, live=None, definition=None) -> ProcessInstance`.
- Store: `ProcessEvent.next_route`. New column in SQLite / Postgres `process_events` (added by
  `ALTER TABLE` when missing) and Django `ProcessEventModel` (migration `0030`).
- `zebra_agent.replay.replay_process(engine, process_id, live, definition, timeout)` creates and
  starts the replay, then returns `workflow_status` plus `replay_of`.
- CLI `manage.py replay_process <id> [--live X]... [--definition file.yaml] [--timeout]` prints
  that status as JSON, and exits 1 when the replay could not start.
- Web: `POST /processes/<id>/replay/` (checkbox `live`) starts the replay in the background
  and redirects to its trace. The trace header shows "Replay of <original>" with a link.

## Risks / trade-offs

- Changes made between steps by something other than a task (e.g. a goal-timeout `__error__`)
  sit in the next task's first event and are not replayed. That's acceptable: they are not task
  effects.
- A live step's new output reaches downstream steps only through properties they read live.
  Replayed downstream steps still restore their recorded values. That is the point of "the rest
  replays".
- Journal growth from the higher cap: prod had 36 truncated values in 2,086 events.

## as-is updates

`specs/zebra-as-is.md` step-journal bullet (now records routes, 256k cap) plus a new replay
bullet. New `specs/replay-debugger-design.md`, linked from `specs/AGENTS.md`.
