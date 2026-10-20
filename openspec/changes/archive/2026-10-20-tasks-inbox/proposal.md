## Why

The **Tasks** and **Activity** nav items open the same page: `/tasks/` only redirects to `/activity/?human_only=true`, and `human_only` is already the default. The Tasks badge counts running goals waiting on a human, but clicking it lands on the whole goal list (running, stale, queued, recent), so you hunt for what needs you. The dashboard strip, the badge and Activity each build "what needs you" a different way, and none of them includes tasks flagged for manual review (#130) as something to act on. Issue #217.

## What Changes

- **`/tasks/` becomes an inbox page** (no redirect): one flat list of everything waiting on a human, oldest first:
  - READY human (`auto: false`) tasks whose process is not finished;
  - tasks flagged `__requires_manual_review__` by recovery (#130).
  Each row shows the task, its goal (linked to the run, or the trace when there is no run), the workflow and how long it has waited. Human rows link to the form (`/tasks/<id>/`); review rows carry the existing Retry / Fail controls. An empty state says nothing is waiting.
- **One read model** (`api/inbox.py`, `inbox_items(store)`) feeds the inbox page, the nav badge (`/nav/needs-you/`) and the dashboard Needs-you strip, so all three always agree.
- The **badge counts inbox items** (tasks), not goals.
- The **dashboard strip** lists inbox items (up to 5, then "N more" linking to `/tasks/`).
- **Activity** is unchanged in behaviour: it stays the goals view. Its nested human-task links already open the forms.
- Docs: `zebra-agent-web/AGENTS.md` (stale `pending_tasks.html` / `/runs/` rows) and the Shell section of `specs/zebra-as-is.md`.

## Capabilities

### New Capabilities
- `tasks-inbox`: the `/tasks/` inbox page and the shared inbox read model.

### Modified Capabilities
- `web-ui-shell`: the Tasks badge counts inbox items.
- `web-ui-key-screens`: the dashboard Needs-you strip lists inbox items.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | Tasks and Activity show different things | Test: `/tasks/` returns 200 with its own template (no redirect); a goal with no human task is on `/activity/` but not `/tasks/`; a manual-review item is on `/tasks/` |
| O2 | The badge, the dashboard strip and the inbox agree | All three come from `inbox_items`; a test with running, finished and review-flagged processes asserts the strip links the same task IDs as the inbox rows, and the badge count equals them |
| O3 | Every inbox item is one click from acting on it, and leaves once acted on | Human rows link to `/tasks/<id>/` and review rows have Retry / Fail; tests: submitting a human task and failing a review task each remove the item from `/tasks/` and the badge; browser smoke of `/tasks/` on prod |
| O4 | The right tasks are in and out | Tests per case: in = READY human task on a running process (top-level, sub-process, or with no in-progress run record) and review-flagged task; out = auto tasks, READY tasks on COMPLETE / FAILED processes, tasks with no definition. Sources are READY vs RUNNING tasks, so an item can't appear twice |
| O5 | The docs match the code | `zebra-agent-web/AGENTS.md` URL / template tables and the zebra-as-is Shell section describe the inbox; `grep pending_tasks.html` finds nothing |

## Impact

- New: `zebra_agent_web/api/inbox.py`, `templates/pages/tasks_inbox.html`, `tests/unit/test_tasks_inbox.py`.
- Changed: `api/web_views.py` (`pending_tasks`, `nav_needs_you`, `dashboard`), `templates/pages/dashboard.html`, `tests/unit/test_human_tasks.py` (the redirect test becomes an inbox test), `tests/unit/test_key_screens.py`.
- No migrations, settings or API changes.
