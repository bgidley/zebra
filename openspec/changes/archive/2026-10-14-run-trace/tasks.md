## 1. Engine journal

- [x] 1.1 `ProcessEvent` / `ProcessEventKind` models and `zebra/core/journal.py` (diff, cap, replay)
- [x] 1.2 Engine emits events at process start/end and task waiting/start/suspend/complete/fail
- [x] 1.3 `StateStore` journal + `list_child_processes` methods; memory, SQLite, Postgres stores
- [x] 1.4 SQLite/Postgres upserts persist parent links set after creation

## 2. Django

- [x] 2.1 `ProcessEventModel`, `parent_process_id` index, migration `0027_process_events`
- [x] 2.2 `DjangoStore` journal + `list_child_processes`; delete cascades events

## 3. Trace page

- [x] 3.1 `api/run_trace.py` builder (tree, steps, current path, snapshots)
- [x] 3.2 Views and routes: process trace, run redirect, properties partial
- [x] 3.3 Templates with live refresh; links from run detail and run status pages

## 4. Tests and docs

- [x] 4.1 `zebra-py/tests/test_journal.py` (memory + SQLite), `tests/unit/test_run_trace.py`
- [x] 4.2 `specs/run-trace-design.md`, `specs/zebra-as-is.md`, AGENTS indexes
