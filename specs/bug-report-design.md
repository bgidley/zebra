# Bug Report Button — Design

## 1. Goal & scope

One-click bug reporting from the web UI that keeps both the user's account and the technical state at that moment, stored in Zebra's workflow history for later review. GitLab [#186](https://gitlab.com/gidley/zebra/-/issues/186). OpenSpec: `bug-report` capability.

Out of scope: screenshots, automatic GitLab issue creation, LLM triage, signed-out pages.

## 2. Data model

No tables or migrations. A report is a **Bug Report** process (`zebra-agent/workflows/bug_report.yaml`, tagged `system`). Process properties:

| Key | Content |
|---|---|
| `bug_report` | `{title, description, expected, steps, severity}`; severity `blocker\|major\|minor\|cosmetic` |
| `technical_context.client` | Browser snapshot: url, title, referrer, user agent, language, time zone, viewport, screen, DPR, colour scheme, seconds on page, last 20 `errors` (onerror, unhandledrejection, console.error) and `failed_requests` (htmx:responseError / sendError). A `note` replaces it when missing, invalid or over 64 KB |
| `technical_context.server` | `received_at`, build `version`, `user`, server-side user agent / referer, `route` (`resolve()` of the page path: view name + kwargs) |
| `technical_context.linked` | State of the process / task / run named in the route kwargs (`process_id`, `task_id`, `run_id`), or a `note` |
| `bug_report_markdown` | Both views rendered for the reviewer |
| `bug_title`, `goal` | Title, and `Bug report: <title>` for dashboard / Tasks labels |
| `__task_output_review` | Reviewer output: `verdict`, `priority`, `issue_url`, `notes` |

## 3. Interfaces

- `POST /bugs/report/` (`bug_report_submit`): form fields above + `client_context` JSON. 200 / 400 / 403 / 500 render `partials/bug_report_result.html`.
- `GET /bugs/` (`bug_reports_page`): last 50 reports with state, severity, verdict, review link and expandable markdown.
- UI: `partials/bug_report_dialog.html` (Alpine, opened by the `open-bug-report` window event), sidebar-footer button and nav entry in `base.html`, `static/js/bug-report.js` (`window.ZebraBugReport.collect()`), loaded un-deferred in `<head>`.
- Module: `zebra_agent_web/api/bug_reports.py`.

## 4. Control flow

Dialog open → snapshot client context into hidden field → POST → validate → resolve route → load linked state (best effort) → `create_process` + `start_process` directly (no daemon queue; no auto tasks, no cost) → process RUNNING with READY `review` task → shows in "needs you" / Tasks → reviewer submits → process COMPLETE → verdict on `/bugs/`.

## 5. Configuration

None.

## 6. Open questions / risks

- Console errors can contain user data; acceptable for the single-user deployment, data stays in Zebra's DB.
- Unreviewed reports stay RUNNING and count in the "needs you" badge, by design.
- Possible follow-ups: optional screenshot, "Create GitLab issue" from the review task.
