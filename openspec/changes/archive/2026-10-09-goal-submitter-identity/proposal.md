# Proposal

Closes #151

## Why

`POST /api/goals/` started the Agent Main Loop without the authenticated user, so the process had
no `__user_id__`. Prod run `e159c6df` logged `consult_knowledge No user_id in process properties`.
Every user-scoped step (knowledge, values profile, ethics context, run ownership) quietly fell
back to "no user" for API goals.

An audit of the other goal entry points found three more gaps:

- The async web views (`/run/execute/`, `/run/queue/`, `/runs/<id>/continue/`) read the identity
  with a sync ORM helper. Inside the event loop that raises `SynchronousOnlyOperation`, which was
  swallowed, so `__user_display_name__` / `__user_identity_id__` were always blank. The direct-run
  paths did not pass identity at all.
- The `queue_goal` task action (Create Goal workflow) did not copy the user onto the queued goal.
- The `zebra goal` CLI and `manage.py run_goal` had no way to run a goal as a user.

## What Changes

- `AgentLoop.process_goal` takes an optional `identity` and stores it as
  `__user_display_name__` / `__user_identity_id__`, the same keys the web `queue_goal` helper uses.
- `execute_goal` resolves `request.user` and identity and passes them through
  `_run_goal_in_background`. The API continue endpoint also passes identity.
- New `goal_identity()` (async) and `goal_identity_sync()` helpers in `api/identity.py`. The async
  web goal views use `goal_identity()`, and `_execute_goal_background` forwards identity.
- `QueueGoalAction` copies `__user_id__`, `__user_display_name__` and `__user_identity_id__` from
  the queuing process.
- `ExecuteGoalWorkflowAction` copies the same keys onto the executed goal workflow, so trust
  gates and knowledge tasks inside it see the user (found via Zebra feedback). Both actions use
  `zebra_tasks/agent/user_context.py::copy_user_properties`.
- `zebra goal --user NAME` and `manage.py run_goal --user NAME` run the goal as that user.

## Capabilities

### New Capabilities
- `goal-submitter-identity`: every goal entry point records who submitted the goal.

## Impact

- `zebra-agent/zebra_agent/loop.py`
- `zebra-agent-web/zebra_agent_web/api/{views.py,web_views.py,identity.py}`, `cli.py`,
  `api/management/commands/run_goal.py`
- `zebra-tasks/zebra_tasks/agent/queue_goal.py`
