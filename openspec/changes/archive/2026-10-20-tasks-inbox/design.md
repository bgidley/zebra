## Context

`/tasks/` has redirected to `/activity/` since the old pages were merged (`c8acfd2`). #160 put a Tasks nav item with a needs-you badge on top of that redirect. The badge and the dashboard strip use `_running_activities` (running root goals with a READY human task; the dashboard caps it at 10 goals). Activity builds its own list from metrics plus engine state. Manual-review tasks (#130) show only inside Activity's goal cards.

## Decisions

**One read model.** `api/inbox.py` exposes `inbox_items(store) -> list[dict]`, oldest first. Items:
- `kind: "human"`: from `store.get_ready_tasks()`, where the task definition has `auto: false` and the task's process is not COMPLETE or FAILED. A finished process can't take a submission, so its leftover READY task is stale state, not work.
- `kind: "review"`: from `manual_review.find_review_tasks(store)`.

Each item has `id`, `kind`, `task_name`, `title` (schema title, human only), `process_id`, `root_process_id`, `run_id`, `goal`, `workflow_name`, `waiting_since`, plus `execution_attempt` for review items. Goal, run and workflow come from walking up to the root process: the first `run_id` seen, the root's `goal`, and the root's `__workflow_name__`, falling back to its definition name. Processes and definitions are cached per call.

**The badge counts tasks, not goals.** With one task per waiting goal (the common case) the number is unchanged. When a goal waits on two things, the badge says 2 and the inbox shows 2 rows, which is the agreement users expect.

**Dashboard strip.** It shows the first 5 inbox items and a "N more" link to `/tasks/`. It replaces `needs_you` built from `_running_activities` (which also stopped at 10 goals). The Running Activities panel keeps using `_running_activities`.

**Review rows** reuse the existing `review_task_retry` / `review_task_fail` endpoints and their swap target (`closest [data-review-task]`).

**Activity is untouched.** Its `human_only` toggle controls whether auto tasks are listed inside goal cards. That's a monitoring view and still useful, so it stays.

## Risks

- `get_ready_tasks()` covers every process. On prod this is a handful of tasks, and per-call caching keeps lookups to one per process.
- READY tasks whose definition is gone are skipped (can't render a form).
