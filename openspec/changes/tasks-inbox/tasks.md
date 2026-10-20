## 1. Read model

- [x] 1.1 `api/inbox.py`: `inbox_items(store)` for human (READY, `auto: false`, process not finished) and review-flagged tasks, oldest first, with goal / run / workflow from the root process
- [x] 1.2 Unit tests: filtering, ordering, finished processes skipped, agent run over but process waiting, review items, sub-process goal resolution

## 2. Pages

- [x] 2.1 `pending_tasks` renders `pages/tasks_inbox.html` (rows, Open / Retry / Fail, empty state, store-failure message)
- [x] 2.2 `nav_needs_you` counts `inbox_items`
- [x] 2.3 Dashboard strip lists the first 5 inbox items and a "N more" link
- [x] 2.4 Replace the `/tasks/` redirect test; view tests for the page, badge and strip agreeing

## 3. Docs and checks

- [x] 3.1 `zebra-agent-web/AGENTS.md` URL / template tables; `specs/zebra-as-is.md` Shell section
- [x] 3.2 ruff, unit tests, `openspec validate tasks-inbox --strict`
- [x] 3.3 Browser check of `/tasks/` and the dashboard on a local server
