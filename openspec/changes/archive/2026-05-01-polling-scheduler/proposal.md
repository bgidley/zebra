## Why

The agent currently only runs workflows when a user submits a goal — it has no ability to act proactively on a schedule. REQ-PRIN-008 requires a polling scheduler so the agent can run routine checks, dream cycles, and knowledge verification autonomously. Closes #27.

## What Changes

- **New**: `routines/*.yaml` — cron-style routine definition files loaded at startup.
- **New**: `zebra-agent/zebra_agent/scheduler/` package replacing the flat `scheduler.py`:
  - `routine.py` — `Routine` dataclass with schedule, workflow reference, and quiet-hours flag.
  - `routine_registry.py` — `RoutineRegistry` discovers routines from `zebra.schedules` entry points and `routines/*.yaml` files.
  - `scheduler_loop.py` — `SchedulerLoop` async task that ticks, evaluates due routines, and creates workflow processes.
  - `goal_queue.py` — existing `GoalScheduler` logic moved here (no functional change).
- **Modified**: Budget daemon (`zebra_agent_web/api/daemon.py`) starts `SchedulerLoop` alongside its existing goal-queue loop.
- **New**: `RoutineStore` interface + Oracle/SQLite implementations persist `last_run`/`next_run` per routine.
- **New**: `routines/` YAML loader and built-in routines (`goal_queue_tick`, `dream_cycle`, `knowledge_verification`).

## Non-goals

- Event-driven triggers (REQ-PRIN-009) — separate feature.
- Dashboard UI for routine management — deferred to a follow-on issue.
- Quiet-hours enforcement — data model only in this iteration; enforcement deferred.

## Capabilities

### New Capabilities

- `polling-scheduler`: Background async loop that evaluates cron/interval routine definitions, checks budget, and creates workflow processes for due routines. Includes `RoutineRegistry` (entry-point + YAML discovery), `RoutineStore` (persistence of last/next run), and built-in routines.

### Modified Capabilities

- (none — the budget daemon integration is an implementation change, not a requirement change)

## Impact

- `zebra-agent/zebra_agent/scheduler.py` → split into `scheduler/` package; imports in `zebra_agent_web` need updating.
- `zebra_agent_web/api/daemon.py` — `SchedulerLoop` started alongside goal-queue daemon.
- New DB migration required for `routine_run` table (last_run, next_run, routine_name).
- New entry-point group `zebra.schedules` in `zebra-agent/pyproject.toml`.
- New `routines/` directory at the `zebra-agent-web` fixtures level for YAML routine definitions.
