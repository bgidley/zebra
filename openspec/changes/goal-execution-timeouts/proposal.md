## Why

`WorkflowEngine.start_process()` runs every auto task inline before returning, so the goal-path timeouts (`execute_goal_workflow` `timeout: 120`, `AgentLoop` `max_wait=300`, daemon `max_wait=600`) only started counting once a run had already finished or parked on a human task. A slow or hung action blocked the daemon indefinitely, held the process lock, and the kill switch could not interrupt it. Issue #142.

## What Changes

- New `WorkflowEngine.start_process_with_timeout(process_id, timeout, cancel_check=None, poll_interval=1.0)`: runs `start_process` as a background task; on timeout, a `cancel_check` reason, or caller cancellation it cancels the chain and fails the process (`fail_process`), releasing the lock.
- `execute_goal_workflow` starts (and re-attaches to CREATED) child workflows through it, bounded by its `timeout`; the Agent Main Loop YAML raises that timeout from 120s to 600s (version 9), since it is now actually enforced.
- `AgentLoop` gains `goal_timeout` (default `DEFAULT_GOAL_TIMEOUT` = 900s) bounding `process_goal`; the Dream Cycle is bounded by `DREAM_CYCLE_TIMEOUT` (600s).
- Daemon `_tick` bounds each goal by the new `GOAL_TIMEOUT_SECONDS` setting (env `ZEBRA_GOAL_TIMEOUT_SECONDS`, default 900) and uses the kill switch as the `cancel_check`, so it now cancels an in-flight auto-only goal.

## Capabilities

### New Capabilities
- `goal-execution-timeouts`: bounded goal execution with timeout and kill-switch cancellation.

### Modified Capabilities
<!-- none -->

## Impact

- `zebra-py/zebra/core/engine.py`, `zebra-tasks/zebra_tasks/agent/execute_workflow.py`, `zebra-agent/zebra_agent/loop.py`, `zebra-agent/workflows/agent_main_loop.yaml`, `zebra-agent-web/zebra_agent_web/api/daemon.py`, `api/agent_engine.py`, `settings.py`.
- Behaviour change: goal workflows running longer than 600s, or full goals longer than 900s, are now failed instead of running unbounded. Time parked on a human task is not counted.
