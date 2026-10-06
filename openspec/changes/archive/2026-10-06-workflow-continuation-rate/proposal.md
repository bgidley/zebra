## Why

#136 computes a per-workflow continuation rate inside the dream-cycle analyzer, but operators can't see it: the web UI and API only show success rate. A workflow that "succeeds" but keeps needing a follow-up is invisible. Issue #137.

## What Changes

- `WorkflowStats` gains `continued_runs` (runs that a later run continues via `extends_run_id`) and a `continuation_rate` property, using the same definition as the #136 analyzer.
- Both metrics stores populate `continued_runs` in `get_stats` / `get_all_stats` (Django: one subquery-filtered `Count`; no migration).
- Web UI: workflow detail page gets a "Continued" stat card; dashboard top-workflows and the workflow library list show "N% continued" next to success rate when a workflow has continued runs.
- API: workflow detail `stats` and the workflow stats endpoint include `continued_runs` and `continuation_rate`.

## Capabilities

### New Capabilities
- `workflow-continuation-rate`: per-workflow continuation rate exposed by the metrics stores, web UI and API.

### Modified Capabilities
<!-- none -->

## Impact

- `zebra-agent/zebra_agent/metrics.py`, `zebra-agent/zebra_agent/storage/metrics.py`, `zebra-agent-web/zebra_agent_web/metrics_store.py`
- `zebra-agent-web/zebra_agent_web/api/web_views.py`, `views.py`, `serializers.py`; templates `pages/dashboard.html`, `pages/workflow_detail.html`, `partials/workflow_library_list.html`
- Additive only: the new dataclass field has a default; API responses gain fields.
