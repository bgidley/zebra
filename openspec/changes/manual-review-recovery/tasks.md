## 1. Engine

- [x] 1.1 `MANUAL_REVIEW_FLAG` constant; `retry_task(task_id, execute=True)` with state checks
- [x] 1.2 `resume_all_processes(max_interrupted_attempts=None)` fails the process at the cap

## 2. Web

- [x] 2.1 `RECOVERY_MAX_INTERRUPTED_ATTEMPTS` setting; daemon passes it to recovery
- [x] 2.2 `api/manual_review.py`: find / retry (background) / fail (process + ancestors)
- [x] 2.3 Activity + run detail (both templates) show flagged tasks with Retry / Fail (HTMX)
- [x] 2.4 REST: `GET /api/review-tasks/`, `POST /api/tasks/<id>/retry/`, `POST /api/tasks/<id>/fail/`

## 3. Tests

- [x] 3.1 Engine: flagging, retry (execute / reset-only / rejects unflagged / rejects non-running process), cap, no-cap
- [x] 3.2 Web: find_review_tasks run resolution, activity + run detail rendering, retry/fail views, REST endpoints incl. 404/409/auth

## 4. Docs

- [x] 4.1 `specs/f8-crash-recovery.md`, `specs/zebra-as-is.md`, settings tables in AGENTS.md files
