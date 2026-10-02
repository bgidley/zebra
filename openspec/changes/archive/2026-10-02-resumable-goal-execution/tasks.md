## 1. Implementation

- [x] 1.1 `execute_goal_workflow`: record `__child_process_id__` on the task before starting the child; re-attach to a still-linked recorded child on re-run (start if CREATED)
- [x] 1.2 Mark `execute_workflow` in `agent_main_loop.yaml` `idempotent: true`; bump to version 7 so installed libraries pick it up
- [x] 1.3 `resume_all_processes`: recover children before parents (`_children_first`)
- [x] 1.4 Daemon: run startup recovery as a background task (`recover_interrupted`), cancel on stop

## 2. Tests

- [x] 2.1 Re-attach to a running child; collect an already-completed child; unlinked recorded child spawns new (`zebra-tasks/tests/test_execute_workflow_resume.py`)
- [x] 2.2 Recovery end-to-end: interrupted goal resumed via `resume_all_processes`, single child
- [x] 2.3 Children-first recovery order (`zebra-py/tests/test_recovery.py`)
- [x] 2.4 Daemon scheduler loop starts while recovery still running; recovery errors swallowed

## 3. Docs

- [x] 3.1 Update `specs/f8-crash-recovery.md` and `specs/zebra-as-is.md`
