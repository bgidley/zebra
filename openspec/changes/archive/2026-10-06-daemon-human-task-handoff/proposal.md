## Why

The budget daemon runs one goal per tick and polls it for up to 10 minutes. A goal that pauses on a human task — the Agent Main Loop's `ethics_dilemma_resolution` form, or an `auto: false` task inside the executed child workflow — blocks the whole queue while it waits. When the 10-minute poll gives up, the daemon logs "will check again next tick", but `GoalScheduler.pick_next()` only selects CREATED processes, so the goal's eventual outcome, cost and `goals_completed` metric are never recorded. `AgentLoop.process_goal()` has the same flaw: it reports "Agent loop timed out" for a goal that is just waiting on a person. Issue #141.

## What Changes

- New `find_pending_human_task(engine, process_id)` helper: returns the first READY `auto: false` task in a process or any RUNNING descendant process, or `None`.
- New `GoalTracker` (zebra-agent scheduler): holds the daemon's in-flight goals, each with its background execution task. It reconciles goals that finished since the last tick (logs done/fail, cost, `goals_completed` metric). It also reports whether a goal is actively executing, which blocks new pickup so that budget pacing stays one goal at a time.
- Daemon `_tick` runs `start_process` as a background task and waits until it finishes **or** parks on a human task; a parked goal stays tracked and the daemon moves on. Goals the daemon starts are marked `__daemon_started__`; after a restart, the tracker seeds itself with RUNNING marked goals so their outcomes are still recorded.
- Kill switch cancels the actively executing goal's background task and fails the process (previously only possible once `start_process` had returned).
- `AgentResult` gains `awaiting_input: bool = False`; `process_goal()` returns it (with the pending task name in `error`) instead of a timeout when the loop is waiting on a human.
- `goals_completed` status label `timeout` is no longer emitted.

## Capabilities

### New Capabilities
- `daemon-goal-handoff`: the daemon hands off goals waiting on humans and reconciles in-flight goals across ticks.

### Modified Capabilities
<!-- none -->

## Impact

- `zebra-agent/zebra_agent/scheduler/` (new `goal_tracker.py`, `human_tasks.py`), `zebra-agent/zebra_agent/loop.py`
- `zebra-agent-web/zebra_agent_web/api/daemon.py`, `api/metrics.py` (label docs)
- Additive: `AgentResult` field has a default; `_tick` gains an optional `tracker` argument.
- Out of scope: bounding execution time (#142), routing failures to assessment (#140).
