## 1. Branch Setup

- [x] 1.1 Create branch `f34/cli-persistent-store` from master

## 2. Extract Shared Queue Helper

- [x] 2.1 Create `zebra-agent-web/zebra_agent_web/api/goals.py` with `async def queue_goal(goal, *, model=None, priority=3, deadline=None, user_id=None, identity=None) -> ProcessInstance` — move the property-assembly + `create_process` logic out of `web_views.run_goal_queue`
- [x] 2.2 Refactor `run_goal_queue` view to parse HTTP input and delegate to `queue_goal()` (behaviour-preserving; keep HTML response as-is)
- [x] 2.3 Unit test `queue_goal()`: mock engine/library; assert properties dict matches the pre-refactor shape (goal, run_id, priority, available_workflows, `__llm_model__`, deadline)

## 3. `zebra` CLI Entry Point

- [x] 3.1 Add `main()` argparse dispatcher to `zebra-agent-web/zebra_agent_web/cli.py` with `goal` and `goals` subcommands, reusing the existing `_load_env()` / `_setup_django()` helpers
- [x] 3.2 Register console script in `zebra-agent-web/pyproject.toml`: `zebra = "zebra_agent_web.cli:main"`, then `uv sync --all-packages`
- [x] 3.3 Add `_check_backend(allow_sqlite)` guard: after `django.setup()`, inspect `connections["default"].vendor`; if not `oracle` and `--allow-sqlite` not passed, print active backend + required `ORACLE_*` vars and exit 1

## 4. `zebra goal` Handler

- [x] 4.1 Implement run mode: `agent_engine.ensure_initialized()` → `agent_loop.process_goal(goal, model=resolved)` with a progress callback printing emitted events; print final output block (success, output, run_id, tokens)
- [x] 4.2 Implement `--queue` mode: call `queue_goal()` from task 2.1, print the created process ID, exit 0
- [x] 4.3 Support `--model` (haiku/sonnet/opus/kimi, default haiku) and `--priority` (1–5, default 3, queue mode only)

## 5. `zebra goals` Handler

- [x] 5.1 Implement `goals` handler: `DjangoMetricsStore.get_recent_runs(limit)`, print table (run_id[:8], workflow_name, goal[:50], success, started_at), `--limit` default 10

## 6. Tests

- [x] 6.1 Unit test backend guard: simulate SQLite vendor → assert exit 1 and message names `ORACLE_DSN`; with `--allow-sqlite` → proceeds
- [x] 6.2 Unit test `goal` handler: mock `agent_engine`; assert `process_goal` called with resolved model; assert queue mode calls `queue_goal()` and prints process ID
- [x] 6.3 Unit test `goals` handler: mock metrics store; assert formatting and limit
- [x] 6.4 Integration test (Oracle, in `tests/test_agent_loop_integration.py` style): invoke the CLI goal handler against the real Oracle schema, then assert the run is returned by `DjangoMetricsStore.get_recent_runs()` — the store the dashboard view reads (issue #34 E2E criterion) — implemented as queue-mode test in `e2e_live/test_cli_integration.py` (no LLM cost, self-cleaning); passed against live Oracle
- [x] 6.5 Run full suite: `uv run pytest zebra-agent/tests/ zebra-tasks/tests/ zebra-agent-web/tests/ --ignore=zebra-agent-web/tests/e2e_live --ignore=zebra-agent-web/tests/e2e -q` (1131 passed; 2 pre-existing smoke failures unchanged)

## 7. Lint, Feedback, Commit

- [x] 7.1 Run `uv run ruff check --fix . && uv run ruff format .`
- [x] 7.2 Run Zebra feedback: `bash scripts/zebra-feedback.sh 34 "CLI with persistent store" "- zebra goal/goals console commands in zebra-agent-web backed by Oracle\n- Oracle backend guard against silent SQLite fallback\n- queue_goal() helper shared by CLI and web view"` (kimi: requirements met)
- [x] 7.3 Commit: `feat: add zebra CLI with Oracle-backed goal/goals commands\n\nCloses #34`
- [x] 7.4 Push branch and verify CI pipeline passes (pipeline #151 green)
