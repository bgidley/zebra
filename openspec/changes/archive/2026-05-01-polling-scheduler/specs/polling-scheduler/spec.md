## ADDED Requirements

### Requirement: Routine definition loading
The system SHALL load routine definitions from YAML files in the `routines/` directory and from Python entry points registered under the `zebra.schedules` group. Each routine definition SHALL specify a name, a schedule (cron expression or `every: Xm/Xh/Xd` interval), and a workflow reference.

#### Scenario: YAML routine is loaded on startup
- **WHEN** a valid `routines/my_routine.yaml` file exists with `name`, `schedule`, and `workflow` fields
- **THEN** `RoutineRegistry` includes `my_routine` in its registered routines

#### Scenario: Invalid YAML routine is skipped with a warning
- **WHEN** a `routines/bad.yaml` file is missing required fields
- **THEN** the system logs a warning and continues loading other routines without raising an exception

#### Scenario: Entry-point routine is discovered
- **WHEN** a Python package registers a routine factory under the `zebra.schedules` entry-point group
- **THEN** `RoutineRegistry` includes that routine alongside YAML-defined routines

### Requirement: Cron and interval schedule evaluation
The system SHALL evaluate whether a routine is due by comparing the current time to its `next_run` timestamp. For cron schedules the next run SHALL be computed using standard cron semantics. For `every: Xm/Xh/Xd` schedules the next run SHALL be computed as `last_run + interval` (or `now` if no `last_run` exists).

#### Scenario: Cron routine fires at scheduled time
- **WHEN** the current time matches or passes a routine's cron-derived `next_run`
- **THEN** the `SchedulerLoop` considers the routine due and dispatches it

#### Scenario: Interval routine fires after elapsed time
- **WHEN** `now >= last_run + interval` for an `every:`-style routine
- **THEN** the `SchedulerLoop` considers the routine due

#### Scenario: Not-yet-due routine is skipped
- **WHEN** `now < next_run` for a routine
- **THEN** the routine is not dispatched during that tick

### Requirement: Routine run persistence
The system SHALL persist each routine's `last_run` and `next_run` timestamps in a `routine_runs` store so that a daemon restart does not re-fire routines that have already run. On startup, if no persisted state exists for a routine, the system SHALL set `next_run` to `now` (so the first tick fires immediately on the first run).

#### Scenario: Restart does not re-fire already-run routine
- **WHEN** the daemon restarts after a routine ran successfully
- **THEN** the `SchedulerLoop` reads the persisted `next_run` and does not fire the routine until that time is reached

#### Scenario: First-ever start fires immediately
- **WHEN** a routine has no persisted `last_run`
- **THEN** it is treated as due on the first tick

### Requirement: Routine creates a workflow process
The system SHALL dispatch a due routine by creating a workflow process via the standard engine path (`engine.create_process` → `engine.start_process`). The process SHALL be tagged with a `__routine__` property set to the routine name.

#### Scenario: Due routine creates a process
- **WHEN** a routine is dispatched by the `SchedulerLoop`
- **THEN** a `ProcessInstance` is created with `properties["__routine__"] == routine_name`

#### Scenario: Routine is skipped when budget is exhausted (budget-aware routines)
- **WHEN** a routine has `budget_aware: true` and the daily budget is exhausted
- **THEN** the routine is not dispatched and a warning is logged

### Requirement: SchedulerLoop runs as background async task
The `SchedulerLoop` SHALL run as an `asyncio` background task started alongside the budget daemon. It SHALL tick on the same `poll_interval` as the daemon. It SHALL stop cleanly when its `stop_event` is set.

#### Scenario: Loop ticks and evaluates routines
- **WHEN** the `SchedulerLoop` is started and `poll_interval` elapses
- **THEN** it evaluates all registered routines against the current time

#### Scenario: Loop stops on stop_event
- **WHEN** the `stop_event` is set
- **THEN** the loop exits within one poll interval

### Requirement: Clock abstraction for testability
The `SchedulerLoop` SHALL accept an injectable clock callable (`Callable[[], datetime]`) defaulting to `datetime.now(UTC)`. Tests SHALL be able to inject a fake clock that advances time programmatically.

#### Scenario: Fake clock advances time in tests
- **WHEN** a `FakeClock` is injected and advanced by 1 minute
- **THEN** an `every: 1m` routine becomes due and is dispatched without wall-clock waiting

### Requirement: Built-in routines
The system SHALL include two built-in routine definitions:
- `goal_queue_tick`: interval-based (every `poll_interval` seconds), wraps existing goal-queue logic, always budget-aware.
- `dream_cycle`: cron-based (`0 3 * * *` by default), references `dream_cycle.yaml` workflow (stub), not budget-aware.

#### Scenario: goal_queue_tick processes the goal queue
- **WHEN** `goal_queue_tick` is dispatched
- **THEN** the highest-priority CREATED process (if any) is started, matching existing daemon behaviour

#### Scenario: dream_cycle fires daily at 03:00
- **WHEN** the clock reaches 03:00 local time and `dream_cycle` has not run today
- **THEN** a `dream_cycle` process is created
