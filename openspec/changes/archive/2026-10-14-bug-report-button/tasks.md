## 1. Workflow
- [x] 1.1 Add `zebra-agent/workflows/bug_report.yaml` (system tag, single human review task)

## 2. Server
- [x] 2.1 `api/bug_reports.py`: validate input, build server context, linked process/run, markdown summary, list recent reports
- [x] 2.2 Views `bug_report_submit` (POST `/bugs/report/`) and `bug_reports` (GET `/bugs/`), routes in `urls.py`

## 3. UI
- [x] 3.1 `static/js/bug-report.js`: buffer console/HTMX errors, collect client context
- [x] 3.2 Dialog partial included in `base.html`, sidebar button, `bug` icon
- [x] 3.3 `pages/bug_reports.html` list page

## 4. Tests and docs
- [x] 4.1 Unit tests for the module, views and workflow
- [x] 4.2 Update `zebra-agent-web/AGENTS.md`, `specs/zebra-as-is.md`
