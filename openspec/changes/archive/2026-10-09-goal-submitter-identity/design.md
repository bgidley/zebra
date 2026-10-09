# Design

## Process properties
The Agent Main Loop process carries the submitter in three keys:
- `__user_id__`: Django user id, or `None`
- `__user_display_name__` and `__user_identity_id__`: the single-user identity from
  `SystemStateModel`

`process_goal` writes the identity keys only when `identity` is given, so callers without a user
(e.g. the CLI without `--user`) behave as before.

## Reading identity
`goal_identity_sync()` and `goal_identity()` both return
`{"user_display_name", "user_identity_id"}` and never raise; on error they return empty strings.
Sync DRF views use the sync helper. Async Django views must use the async helper, because the sync
ORM call fails inside a running event loop. `web_views._identity_context()` now delegates to the
sync helper and stays for sync template contexts.

## Entry points
| Entry point | user_id | identity |
|---|---|---|
| `POST /api/goals/` | `request.user` | `goal_identity_sync()` |
| `POST /api/runs/<id>/continue/` | `request.user` (already) | `goal_identity_sync()` |
| `/run/execute/`, `/runs/<id>/continue/` (now) | `request.user` (already) | `await goal_identity()` |
| `/run/queue/`, `/runs/<id>/continue/` (queue) | `request.user` (already) | `await goal_identity()` |
| `queue_goal` action | copied from the parent process | copied from the parent process |
| `execute_goal_workflow` (child goal workflow) | copied from the Agent Main Loop | copied |
| `zebra goal`, `manage.py run_goal` | `--user NAME` | `goal_identity()` when `--user` is given |

The budget daemon starts processes that already carry these properties, so it needs no change.
