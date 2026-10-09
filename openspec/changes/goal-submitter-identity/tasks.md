# Tasks

Branch: `f151/api-goals-user-id`. Commits reference #151.

## 1. Agent loop

- [x] 1.1 `AgentLoop.process_goal` accepts `identity` and stores the identity keys; verify with new tests in `zebra-agent/tests/test_loop.py`

## 2. Web and API entry points

- [x] 2.1 Add `goal_identity()` / `goal_identity_sync()` to `api/identity.py`
- [x] 2.2 `execute_goal` passes `user_id` + identity through `_run_goal_in_background`; API continue passes identity
- [x] 2.3 Async web goal views use `await goal_identity()`; `_execute_goal_background` forwards identity
- [x] 2.4 Tests in `zebra-agent-web/tests/unit/test_goal_user_id.py`

## 3. Other entry points

- [x] 3.1 `QueueGoalAction` copies the user keys from the parent; tests in `zebra-tasks/tests/test_queue_goal.py`
- [x] 3.2 `zebra goal --user` and `manage.py run_goal --user`

## 4. Delivery

- [x] 4.1 Update `specs/zebra-as-is.md` and AGENTS.md; run `openspec validate goal-submitter-identity --strict`
- [ ] 4.2 Run lint, format and the test suites; get CI green; run Zebra feedback; merge `Closes #151`
