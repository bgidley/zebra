## Why

Debugging a failed workflow means re-running it live: new spend, different answers, often no
repro. Zebra asked to "re-run a failed workflow with recorded LLM and tool outputs, so I can
debug myself deterministically." Closes #170. The step journal (#184) already records each
task's effect; it lacks the chosen route and truncates values over 16,000 chars.

## What Changes

- **Record**: journal events gain `next_route`; the value cap rises to 256,000 chars.
- **Replay**: `WorkflowEngine.create_replay(process_id, live, definition)` makes a new process
  from a finished one. Each step is served from the original's journal (property changes,
  output, route, success/error); no action runs, human and subflow steps included. Cost keys
  are not copied.
- **Override**: `live` steps, and steps changed in a replacement definition, run for real.
- **Divergence**: an unrecorded or truncated step fails, naming it.
- **CLI** `manage.py replay_process <id> [--live step]... [--definition file.yaml]`; **UI**
  Replay form on finished processes in the step trace.

## Non-goals

- Recursive replay of subflows (replay the subflow itself instead); LLM-call-level recording
  inside a step; journal pruning; choosing a definition in the UI.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | A failed process can be replayed from the CLI and the UI with zero LLM spend when no step is live | Engine test: an action that adds cost and counts its calls is never called and the replay has no `__total_cost__`; prod `replay_process` and the trace's Replay button end the same way |
| O2 | Replaying an unchanged workflow reproduces the original outcome and leaves the original untouched | Engine tests (straight, looping, retried, human and subflow steps): same end state, error and workflow properties, no action runs, the original's process and journal unchanged; a prod replay of a failed run fails at the same step |
| O3 | One step can run live while the rest replays | Tests: only the `live` step's action is called, its output reaches the next step, a step whose definition changed in a replacement definition runs live, and a live step routing somewhere the original never went hits the O4 error |
| O4 | A replay that leaves the recording fails loudly, naming the step | Tests: a missing run and a recorded value carrying the journal's `__journal_truncated__` marker each fail with "Replay cannot serve step '<id>'" and "Run it live"; an old event without `next_route` follows the path the original took |
| O5 | New runs record everything replay needs | Store round-trip tests (in-memory, SQLite, Django; Postgres where available): `next_route` survives, and a value one character under the 256,000 cap is kept whole while one over is truncated |
