## Why

When something goes wrong in the web UI there is no way to say so from inside the app. Problems get described later from memory, without the page, the build, or the browser errors that would explain them. We want a one-click report that keeps both what the user saw and what the system knew at that moment, stored in Zebra itself so it can be reviewed later. Issue #186.

## What Changes

- "Report a bug" button in the sidebar footer of every signed-in page. It opens a dialog asking for a title, what happened, what was expected, steps to reproduce and how bad it is.
- The browser silently adds technical context: page URL and title, referrer, user agent, language, viewport and screen size, time zone, the last JS console errors and failed HTMX requests on the page.
- The server adds: build version, user, server time, the resolved route and its arguments, and the state of any process, task or run the page was showing.
- Submitting starts a new system workflow, **Bug Report**, whose properties hold the user's report, the technical context and a markdown summary. The report is stored in the workflow history like any other process.
- The workflow's one task is a human review task ("Review Bug Report"): it shows the summary and asks the reviewer for a verdict, priority, an optional issue link and notes. It appears in the Tasks / "needs you" list.
- New `/bugs/` page lists recent reports with their state and review outcome.

## Capabilities

### New Capabilities
- `bug-report`: capture a bug report from the web UI and hold it for review as a workflow.

### Modified Capabilities
<!-- none -->

## Impact

- New `zebra-agent/workflows/bug_report.yaml` (tagged `system`, so the goal selector never picks it).
- New `zebra-agent-web/zebra_agent_web/api/bug_reports.py`; views `bug_report_submit`, `bug_reports` in `web_views.py`; routes `/bugs/` and `/bugs/report/`.
- Templates: `partials/bug_report_dialog.html` (included in `base.html`), `pages/bug_reports.html`; script `static/js/bug-report.js`; vendored Phosphor `bug` icon.
- No migrations. No LLM calls, so reporting costs nothing.
