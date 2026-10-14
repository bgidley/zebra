## Context

The web UI is Django + HTMX + Alpine. Workflows started from the UI (e.g. the values wizard) use `library.get_workflow()` + `engine.create_process()` + `start_process()`. Human tasks (`auto: false`) render a JSON Schema form; `readOnly` string fields render as markdown. Any running process with a READY human task shows in the dashboard and the "needs you" badge.

## Goals / Non-Goals

**Goals:** capture the user's view and a technical view in one step; store it as a process in the workflow history; give a reviewer a place to record a verdict.

**Non-Goals:** screenshots; creating GitLab issues automatically; LLM triage; reports from signed-out pages.

## Decisions

- **A workflow, not a table.** The report is a "Bug Report" process. Its properties are the record (`bug_report`, `technical_context`, `bug_report_markdown`, `bug_title`); the review outcome is `__task_output_review`. No migration, and review uses the existing human-task machinery.
- **Started directly, not queued.** It has no auto tasks and costs nothing, so it bypasses the budget daemon, like the values wizard. The `goal` property is set to `Bug report: <title>` so the dashboard and Tasks list label it clearly.
- **Context is collected in two halves.** The browser knows the page and its errors; the server knows the build, user and the process behind the page. `static/js/bug-report.js` loads in `<head>` (not deferred) so it buffers `window.onerror`, `unhandledrejection`, `console.error` and `htmx:responseError` / `htmx:sendError` from page load, keeping the last 20 of each.
- **Bounded input.** User text fields are trimmed and capped; the client context must be a JSON object under 64 KB, otherwise it is replaced with a note. Nothing from cookies or storage is captured.
- **Linked state is best effort.** The page path is resolved with Django's `resolve()`. A `process_id` or `task_id` argument loads the process (state, workflow name, `__error__`, `__failed_task__`); a `run_id` loads the metrics run. Any failure is recorded as a note, never blocks the report.

## Risks / Trade-offs

- Console errors may contain user data. Acceptable: single-user deployment, data stays in Zebra's own DB.
- Unreviewed reports stay RUNNING and count in the "needs you" badge. That is the point: they ask for review.
