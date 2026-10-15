## 1. Engine

- [x] 1.1 `start_process(process_id, start_task_ids=None)`; pass through `start_process_with_timeout`
- [x] 1.2 Tests: start at a later task, at a human task, on two branches, unknown id raises

## 2. Goal workflow resume

- [x] 2.1 `execute_goal_workflow`: find the failed child of a `same_workflow` retry, carry state, start at unfinished tasks, record `__resumed_from__`
- [x] 2.2 F129 re-attach starts a CREATED resumed child at the recorded tasks
- [x] 2.3 Tests: resume without re-asking; fresh start for success / other decision / changed workflow / unknown run

## 3. Docs

- [x] 3.1 `zebra-tasks/AGENTS.md`, `specs/zebra-as-is.md`
