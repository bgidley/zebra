## Context

The budget daemon (`zebra_agent_web/api/daemon.py`) runs a single loop: pick a goal → check budget → execute → repeat. It has no notion of time-based scheduling — only priority-ordered queue draining. The `GoalScheduler` (`zebra_agent/scheduler.py`) is a scoring helper, not a scheduler in the time-based sense.

REQ-PRIN-008 requires a cron/interval scheduler that fires named routines, each of which creates a workflow process. The goal-queue loop should become one built-in routine (`goal_queue_tick`) rather than a peer loop.

## Goals / Non-Goals

**Goals:**
- `SchedulerLoop` async task runs alongside (or instead of) the raw daemon loop, ticking on `poll_interval`.
- Routines are discovered from YAML files (`routines/*.yaml`) and `zebra.schedules` entry points.
- `RoutineRunStore` persists `last_run`/`next_run` per routine so restarts don't re-fire already-run routines.
- Injectable clock abstraction so the E2E test can advance time without sleeping.
- `scheduler.py` → `scheduler/` package; existing `GoalScheduler` import path still works via `__init__.py` re-export.

**Non-Goals:**
- Quiet-hours enforcement (data model field present, logic deferred).
- Dashboard/CLI management of routines.
- Event-driven triggers (REQ-PRIN-009).

## Decisions

### 1. `SchedulerLoop` replaces `run_daemon_loop` as the primary loop

**Decision**: `daemon.py::run_daemon_loop` starts a `SchedulerLoop` and awaits it, instead of running its own goal-queue loop directly. The existing goal-queue logic becomes the `goal_queue_tick` built-in routine.

**Why**: Avoids two parallel timers. All scheduled work goes through one tick path. Adding a new routine is adding a YAML file, not modifying the daemon.

**Alternative considered**: Keep daemon loop untouched, add a second async task for routines. Rejected — two ticking loops with separate poll intervals drift and double-schedule; harder to reason about.

### 2. Schedule format: cron string OR `every: Xm/Xh/Xd`

**Decision**: Each routine specifies either `cron: "0 3 * * *"` or `every: 30m`. The `SchedulerLoop` uses `croniter` (already available as a transitive dep via `celery`-adjacent libs) for cron evaluation, and simple `timedelta` arithmetic for `every:` intervals.

**Why**: Cron covers calendar-aligned schedules (daily at 03:00); `every:` covers simple polling without cron syntax overhead. Both are common in user-facing scheduler configs.

**Alternative considered**: Only cron strings. Rejected — `every: 30m` is more readable for the common polling case and avoids cron parsing errors.

### 3. `RoutineRunStore` for persistence

**Decision**: New store interface `RoutineRunStore` with `get_run(routine_name) → RoutineRun | None` and `upsert_run(run: RoutineRun) → None`. Oracle and SQLite implementations. New migration `0014_routine_runs.py`.

Stored fields: `routine_name (PK)`, `last_run (ISO datetime)`, `next_run (ISO datetime)`, `last_status (str)`.

**Why**: Routines need persistent `next_run` so a daemon restart doesn't re-fire today's already-run `dream_cycle`. Storing in process properties would require querying all processes to find last run times — too expensive.

**Alternative considered**: Store `last_run` in a JSON file on disk. Rejected — doesn't work in multi-process deployments.

### 4. Clock abstraction

**Decision**: `SchedulerLoop` accepts an optional `clock: Callable[[], datetime]` argument defaulting to `lambda: datetime.now(UTC)`. Tests inject a `FakeClock` that `advance(minutes=N)` moves forward.

**Why**: The E2E test requirement is "routine fires in test clock" — wall-clock sleeping would make the test take 60+ seconds. Fake clock makes it deterministic and fast.

### 5. `scheduler/` package — backward-compatible re-export

**Decision**: `zebra_agent/scheduler/__init__.py` re-exports `GoalScheduler` from `scheduler/goal_queue.py`. Existing `from zebra_agent.scheduler import GoalScheduler` continues to work.

**Why**: `daemon.py` and management commands import `GoalScheduler` directly. Avoids a flag-day refactor of all importers.

## Risks / Trade-offs

- [croniter not installed] → `croniter` must be added to `zebra-agent/pyproject.toml`. If not available at runtime, cron routines will fail at parse time. Mitigation: add to `[project.dependencies]` and verify in unit test.
- [Missed-schedule catch-up] → If the daemon was down for 3 days, `dream_cycle` has 3 missed runs. Default policy is `skip` (just set `next_run` from now). Per-routine `on_missed: catchup|skip` can be added later.
- [Oracle migration] → New `routine_runs` table. Migration must be idempotent (CREATE TABLE IF NOT EXISTS equivalent). Tested against E2E Oracle schema.

## Migration Plan

1. Add migration `0014_routine_runs.py` for the `routine_runs` table.
2. Move `scheduler.py` → `scheduler/goal_queue.py`; add `scheduler/__init__.py` re-exporting `GoalScheduler`.
3. Add `SchedulerLoop`, `RoutineRegistry`, `Routine` dataclass, `RoutineRunStore`.
4. Update `daemon.py::run_daemon_loop` to delegate to `SchedulerLoop`.
5. Add built-in routines: `goal_queue_tick.yaml`, `dream_cycle.yaml`.
6. E2E test: inject `FakeClock`, advance 1 minute, assert routine process was created.

Rollback: revert `daemon.py` to call old loop directly; `scheduler/__init__.py` re-export means no import changes needed elsewhere.

## Open Questions

- Should `dream_cycle.yaml` point to an existing workflow definition, or is that workflow also created in this issue? (Assumption: create a stub `dream_cycle.yaml` workflow that is a no-op placeholder.)
- `croniter` vs `cronsim` — verify `croniter` is available transitively or pick the lighter `cronsim` (pure Python, no deps).
