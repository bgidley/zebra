## 1. Engine

- [x] 1.1 Add `WorkflowEngine.start_process_with_timeout` (deadline, cancel_check, caller cancellation → `fail_process`)
- [x] 1.2 Tests: completes, times out, releases lock, cancel_check, manual pause, caller cancel

## 2. Goal path

- [x] 2.1 `execute_goal_workflow` starts/re-attaches children via the bounded start; coerce `timeout` to float
- [x] 2.2 Agent Main Loop YAML: child `timeout` 120 → 600, version 9
- [x] 2.3 `AgentLoop(goal_timeout=DEFAULT_GOAL_TIMEOUT)` bounds `process_goal`; Dream Cycle bounded by `DREAM_CYCLE_TIMEOUT`
- [x] 2.4 Daemon `_tick(goal_timeout=…)` with kill switch as `cancel_check`; `GOAL_TIMEOUT_SECONDS` setting wired into daemon and web `AgentLoop`

## 3. Tests and docs

- [x] 3.1 Real-engine tests for execute_goal_workflow, AgentLoop and daemon timeouts + kill switch
- [x] 3.2 Update `specs/zebra-as-is.md`, root and package AGENTS.md settings tables
