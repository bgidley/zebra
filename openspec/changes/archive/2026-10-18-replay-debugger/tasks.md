Branch: `f170/replay-debugger`

## 1. Recording

- [x] 1.1 `ProcessEvent.next_route`; engine writes it on task end; cap to 256,000 chars
- [x] 1.2 SQLite / Postgres column (+ `ALTER TABLE` for existing DBs), in-memory, Django model + migration 0030 + store

## 2. Replay engine

- [x] 2.1 `zebra/core/replay.py`: `RecordedStep`, `recorded_steps` (fold, route inference), `ReplayError`
- [x] 2.2 `WorkflowEngine.create_replay` (+ `continue_live`); serving in `_run_task`; `_runs_itself` for manual steps
- [x] 2.3 Tests: unchanged replay, zero spend, routes, human steps, subflow steps, live override, changed definition, divergence, truncated value, running process

## 3. Entry points

- [x] 3.1 `zebra_agent.replay.replay_process`; `manage.py replay_process`
- [x] 3.2 `POST /processes/<id>/replay/`, Replay form on the trace, "Replay of" banner
- [x] 3.3 Tests: CLI command, view, store round trip

## 4. Docs & delivery

- [x] 4.1 `specs/replay-debugger-design.md`, `specs/AGENTS.md`, `specs/zebra-as-is.md`, package AGENTS.md
- [x] 4.2 Run lint + format (`uv run ruff check --fix . && uv run ruff format .`), full tests
- [x] 4.3 Prod-data dry run: 80 recent finished prod processes replayed locally, no actions registered: 72 identical, 7 stop loudly on pre-#170 truncated values, 1 differs only by a property edited outside the engine after it finished. Live prod CLI + UI replay is checked in the post-deploy outcome review
