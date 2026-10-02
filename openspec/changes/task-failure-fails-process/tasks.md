## 1. Reproduce

- [x] 1.1 Failing tests in `zebra-py/tests/test_task_failure.py`: auto fail, raise, parallel branch, after `complete_task`, after `resume_all_processes`, human task failed, handled-routing control

## 2. Implementation

- [x] 2.1 `transition_task` completion check: FAILED task with no active tasks → `_fail_process_for_task`
- [x] 2.2 `_fail_process_for_task` sets FAILED, `completed_at`, `__error__`, `__failed_task__`
- [x] 2.3 Update `test_full_coverage.py` tests that pinned the old COMPLETE outcome

## 3. Parent reporting

- [x] 3.1 Real-engine test that `execute_goal_workflow` fails when the child task fails

## 4. Docs

- [x] 4.1 Update `specs/zebra-as-is.md` process lifecycle
