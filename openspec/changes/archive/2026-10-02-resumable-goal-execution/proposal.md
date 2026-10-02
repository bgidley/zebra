## Why

Goals submitted via `POST /api/goals/` run `agent_loop.process_goal` in a daemon thread inside
Daphne. A redeploy kills that thread: the Agent Main Loop process stays `RUNNING` with its
`execute_workflow` task `RUNNING`, while the child workflow process it spawned carries on (or
finishes) with nobody attached. On restart, `resume_all_processes` treats the interrupted
`execute_workflow` as non-idempotent and flags it for manual review, so the goal is stuck forever
(verified in prod 2026-10-02). Issue #129.

## What Changes

- `execute_goal_workflow` records the child process id on its task (`__child_process_id__`)
  before starting the child. When the task runs again it re-attaches to that child (if it is still
  linked via `parent_process_id` / `parent_task_id`) instead of spawning a duplicate; a child that
  already finished is collected immediately.
- The Agent Main Loop's `execute_workflow` task is declared `idempotent: true` (the existing
  task-definition hint `_is_task_idempotent` honours), so recovery resets it to READY and re-drives
  it instead of flagging it.
- `resume_all_processes` recovers child processes before their parents, so a re-attached parent
  waits on a child that is already being driven.
- The daemon runs startup recovery as a background asyncio task, so re-driving a long goal does not
  delay the scheduler loop.

## Capabilities

### New Capabilities

- `goal-crash-recovery`: goals interrupted mid-execution resume after a restart without duplicating
  their executed workflow.

### Modified Capabilities

_(none)_

## Non-goals

- Moving `/api/goals/` onto the daemon goal queue (see design.md for why).
- UI/API for tasks flagged `__requires_manual_review__` (#130).
- Making other actions resumable (LLM calls etc. stay non-idempotent).

## Impact

- `zebra-tasks/zebra_tasks/agent/execute_workflow.py`
- `zebra-agent/workflows/agent_main_loop.yaml`
- `zebra-py/zebra/core/engine.py` (`resume_all_processes` ordering only)
- `zebra-agent-web/zebra_agent_web/api/daemon.py`
