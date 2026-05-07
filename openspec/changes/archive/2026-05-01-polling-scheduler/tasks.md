## 1. Branch and dependency setup

- [x] 1.1 Create feature branch `f27/polling-scheduler` from master
- [x] 1.2 Add `croniter` (or `cronsim`) to `zebra-agent/pyproject.toml` dependencies and run `uv sync --all-packages`

## 2. Scheduler package refactor

- [x] 2.1 Create `zebra-agent/zebra_agent/scheduler/` package; move `scheduler.py` → `scheduler/goal_queue.py` (rename `GoalScheduler` stays the same)
- [x] 2.2 Add `zebra-agent/zebra_agent/scheduler/__init__.py` re-exporting `GoalScheduler` for backward compatibility
- [x] 2.3 Verify existing `GoalScheduler` imports in `daemon.py` and tests still resolve without change

## 3. Routine data model

- [x] 3.1 Create `zebra-agent/zebra_agent/scheduler/routine.py` with `Routine` dataclass: `name`, `schedule` (cron string or `every: Xm/Xh/Xd`), `workflow`, `budget_aware`, `quiet_hours_ok`, `on_missed`
- [x] 3.2 Create `RoutineRun` dataclass: `routine_name`, `last_run`, `next_run`, `last_status`
- [x] 3.3 Write unit tests for cron `next_run` computation and `every:` interval computation (no DB needed)

## 4. RoutineRunStore

- [x] 4.1 Define `RoutineRunStore` abstract interface in `zebra-agent/zebra_agent/scheduler/store.py` with `get_run` / `upsert_run` methods
- [x] 4.2 Implement `InMemoryRoutineRunStore` (for tests)
- [x] 4.3 Implement `DjangoRoutineRunStore` (Oracle/SQLite) in `zebra-agent-web/zebra_agent_web/` using a new Django model `RoutineRunModel`
- [x] 4.4 Write migration `0014_routine_runs.py` for the `routine_runs` table
- [x] 4.5 Write unit tests for `InMemoryRoutineRunStore` get/upsert round-trip

## 5. RoutineRegistry

- [x] 5.1 Create `zebra-agent/zebra_agent/scheduler/registry.py` with `RoutineRegistry` that loads from `zebra.schedules` entry points and `routines/*.yaml` files
- [x] 5.2 Write YAML loader: validate required fields (`name`, `schedule`, `workflow`), log and skip invalid files
- [x] 5.3 Register entry-point group `zebra.schedules` in `zebra-agent/pyproject.toml`
- [x] 5.4 Write unit tests for registry: valid YAML loaded, invalid YAML skipped with warning

## 6. SchedulerLoop

- [x] 6.1 Create `zebra-agent/zebra_agent/scheduler/loop.py` with `SchedulerLoop` class accepting `registry`, `store`, `engine`, `clock`, `stop_event`, `poll_interval`
- [x] 6.2 Implement tick logic: load due routines, check budget (if `budget_aware`), create and start process, upsert `last_run`/`next_run`
- [x] 6.3 Implement `FakeClock` helper in `zebra-agent/zebra_agent/scheduler/testing.py` with `advance(seconds/minutes)` method
- [x] 6.4 Write unit tests for `SchedulerLoop`: due routine fires, not-yet-due routine skipped, budget-exhausted routine skipped
- [x] 6.5 Write unit test for `FakeClock`: advancing time causes `every: 1m` routine to become due

## 7. Built-in routines

- [x] 7.1 Create `zebra-agent-web/fixtures/routines/goal_queue_tick.yaml` (every `poll_interval`s, budget_aware: true) and implement dispatch to `GoalScheduler`
- [x] 7.2 Create `zebra-agent-web/fixtures/routines/dream_cycle.yaml` (cron: `0 3 * * *`, budget_aware: false) referencing stub `dream_cycle` workflow
- [x] 7.3 Create stub `zebra-agent-web/fixtures/workflows/dream_cycle.yaml` (single no-op task) — not needed, dream_cycle.yaml already exists in zebra-agent/workflows/

## 8. Daemon integration

- [x] 8.1 Update `zebra-agent-web/zebra_agent_web/api/daemon.py::run_daemon_loop` to instantiate `SchedulerLoop` (with `DjangoRoutineRunStore`) and await it instead of running the raw goal-queue loop
- [x] 8.2 Ensure `DaemonStarterMiddleware` in `asgi.py` still starts correctly (no changes expected, but verify)
- [x] 8.3 Update `zebra-agent-web/zebra_agent_web/management/commands/run_daemon.py` if it references the old daemon loop directly

## 9. E2E test

- [x] 9.1 Write E2E test: inject `FakeClock`, register a 1-minute `every:` routine, advance clock 1 minute, assert a process with `__routine__ == routine_name` was created and started

## 10. Documentation and cleanup

- [x] 10.1 Update `specs/zebra-as-is.md`: change polling-scheduler gap to "Implemented", add `scheduler/` package description
- [x] 10.2 Run `uv run ruff check --fix . && uv run ruff format .`
- [x] 10.3 Run full test suite `uv run pytest` — all passing
- [x] 10.4 Commit with `feat: add polling scheduler (SchedulerLoop + RoutineRegistry)\n\nCloses #27`
- [x] 10.5 Push to GitLab, verify CI pipeline green (`lint → unit → e2e`)
- [x] 10.6 Push branch to GitHub, open PR targeting master
