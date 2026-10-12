## Why

The most-used screens still had the old template layout: four coloured stat tiles that are usually 0 on the dashboard, eight identical form cards on Trust, a ~9,800px raw YAML dump on workflow detail, and a Run Goal form built from three full-width selects. Run pages also scrolled sideways on phones. This recomposes them around what the owner actually scans for, on the frame tokens from #159/#160. Issue #162 (also contributes to #36).

## What Changes

- **Dashboard**: a "Needs you" strip for goals waiting on a human task leads the page; one vitals panel (spend against the paced budget with a hatched allowance band, success rate, queue); then Running Activities and Recent Runs, with On my mind, Trust by Domain and Top Workflows alongside. State dots instead of coloured pills; money via `|usd`; compact `|ago` times. The stat-card component is removed.
- **Trust**: one table, one form per domain, with a segmented control (radio inputs named `level`) and a reason field plus Save that appear once the level changes. The emergency override becomes a guarded outline danger button, hidden once Zebra is freed. Agent suggestion evidence is shown as Zebra's words.
- **Workflow detail**: compact stats, then the ordered steps (following routings from the first task) beside a structure diagram drawn at natural width, with the YAML behind a "Definition" disclosure.
- **Run Goal**: a larger goal field, a compact options row (model, priority, deadline), then the actions.
- **Run pages**: task panel headers shrink on phones (truncated name, task id hidden below `sm`), removing the sideways scroll.

No URL, form field, `data-testid` or HTMX target changes.

## Capabilities

### New Capabilities
- `web-ui-key-screens`: layout and behaviour of the redesigned dashboard, Trust, workflow detail and Run Goal screens.

### Modified Capabilities
<!-- none -->

## Impact

- Templates: `pages/dashboard.html`, `trust.html`, `workflow_detail.html`, `run_goal.html`, `run_detail.html`, `run_pending.html`, `components/thought.html`; removed `components/stat_card.html`.
- `web_views.py`: `_budget_bars()`, `needs_you` context, `_workflow_structure()`.
- `format_tags.py`: `ago` filter.
