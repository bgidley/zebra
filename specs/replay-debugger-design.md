# Replay debugger (#170)

## 1. Goal and scope

Re-run a finished (usually failed) process from what it recorded, so a failure reproduces exactly
at no LLM cost, and optionally run one step live while the rest replays. Issue
[#170](https://gitlab.com/gidley/zebra/-/work_items/170); OpenSpec change `replay-debugger`.

The recording is the step journal (#184, [run-trace-design.md](run-trace-design.md)); there is
no separate store. Not in scope: recursive replay of subflows (a recorded subflow step is
served as its final result; replay the subflow itself from its trace), LLM-call-level
recording inside a step, journal pruning, choosing a replacement definition in the UI.

## 2. Data model

- `ProcessEvent.next_route` (nullable): written on `task_completed` / `task_failed` from
  `task.result`. Columns: SQLite / Postgres `process_events.next_route` (added with
  `ALTER TABLE` when an older table lacks it), Django `ProcessEventModel.next_route`
  (migration `0030_process_event_next_route`).
- `journal.MAX_JOURNAL_VALUE_CHARS` 16,000 → 256,000. Diffs hold only changed values, so a
  large value is written once per change. Before this, prod had 36 truncated values in
  2,086 events.
- Replay marker, process property `__replay__`:
  `{of: original id, live: [step ids], continue_live: bool, served: {step id: count}}`.
  The counter lives in the process, so a restarted engine continues a replay correctly.

## 3. Interfaces

| Piece | What it is |
|---|---|
| `zebra/core/replay.py` | `RecordedStep` (`success`, `output`, `next_route`, `error`, folded `changed` / `removed`, `truncated_keys()`, `apply()`), `recorded_steps(events, definition)`, `starting_properties`, `changed_steps`, `cannot_serve`, `ReplayError`, `REPLAY_KEY`, `UNREPLAYED_KEYS` |
| `WorkflowEngine.create_replay(process_id, live=None, definition=None, continue_live=False)` | New root process in CREATED with the original's starting properties minus `run_id` and spend keys. Raises `ReplayError` for an unfinished process, no journal, or an unknown live step |
| `zebra_agent.replay.replay_process` / `replay_status` | Create, run, and report: `workflow_status` plus `replay_of`, `live`, `cost` |
| `manage.py replay_process <id> [--live STEP]... [--definition FILE] [--continue-live] [--timeout]` | JSON status. Exits 1 (`status: error`) when the replay cannot start. Warns on stderr when anything runs live |
| `POST /processes/<id>/replay/` (`process_replay`) | Form fields `live` (repeatable) and `continue_live`. Creates the replay on the agent engine, runs it in the background, redirects to its trace. 400 with the `ReplayError` message |
| Step trace | "Replay this process" form on each finished process with a journal (one checkbox per step it ran, a continue-live checkbox, a live-cost warning). A replay's trace has a "Replay of …" banner (`TraceProcess.replay_of`, `replay_live`, `can_replay`, `step_choices`) |

## 4. Control flow

**Recorded step**: the events of one task instance, in order of first appearance. Instances
without a terminal event (interrupted) are skipped. The first event's diff is what happened
before the task began, so it is excluded and the rest are folded. A suspend/resume or
retried instance therefore yields its whole effect. `output` is the `__task_output_<id>` in the
state after the terminal event. For events from before #170 with no `next_route`, the route is
inferred: the named serial routing whose destination the original started next (or the only
terminal named routing). That reproduces the path the original took.

**Serving**: `_run_task` checks the marker. A non-live step calls `_serve_recorded`, which takes
occurrence `n` of that step from the recording (cached per original in `engine._recordings`),
applies it to the process properties (skipping `__total_cost__`, `__total_tokens__` and
`__token_history__`), saves, bumps `served`, and returns
`TaskResult(success, output, next_route, error)`. The engine then stores the output, journals
and routes exactly as it would live, so joins, failures and completion behave the same.
`_runs_itself(task_def, process)` replaces the five `task_def.auto` checks, so served human
steps run inline (no `task_waiting`). A live human step, or an unrecorded one under
`continue_live`, waits for a person.

**Divergence**: no recording for occurrence `n`, or a recording carrying the
`__journal_truncated__` marker, makes the step fail with
`Replay cannot serve step '<id>' (run #n): <reason>. Run it live to continue.` If the replay has
`continue_live`, an unrecorded step runs live instead (used after fixing a failing step live).

**Replacement definition**: saved under `<id>-replay-<hex>`, so the original is untouched.
Steps that are new or differ (`TaskDefinition` inequality) join `live`.

## 5. Configuration

None. The web replay uses the agent loop's `goal_timeout` (`GOAL_TIMEOUT_SECONDS`).

## 6. Open questions / risks

- Changes made between steps by something other than a task (a goal-timeout `__error__`, a web
  edit) sit in the next task's first event and are not replayed.
- Replayed downstream steps restore their recorded values even after a live step changed its
  output; only steps that read live (or run live) see the new value.
- Live steps have real side effects (notifications, writes). The CLI and form warn; nothing
  sandboxes them.
- A replay is not a run: it has no `run_id`, so it never appears in activity or metrics, and
  starts no postmortem.
  The goal queue (`GoalScheduler.get_pending_goals`) skips `__replay__` processes, so the
  daemon never starts one that is briefly CREATED.
- Journal growth from the higher cap. Still no pruning.
