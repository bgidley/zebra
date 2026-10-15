## Why

The dream cycle runs every night and can create, modify and retire workflows, but nothing in the web UI shows what it did. The only record is a "Dream Cycle" process's properties, which you can read only by querying the database. Operators need one screen showing what recent cycles found and changed. Issue #154.

## What Changes

- New `/dreams/` page ("Dream Cycles" in the nav) listing the 20 most recent Dream Cycle processes, newest first.
- Summary stats: latest health score, completed/failed cycle counts, workflow changes applied, workflows retired, and a health-score trend strip.
- Per cycle: start time, status, duration, health score, runs analyzed, changes applied / rejected, retirements (with rule and reason), continuations, the LLM `dream_summary` (rendered as markdown), and for failed cycles the error and failing task.
- Header shows the `dream_cycle` routine's next scheduled run.
- Read-only. No new data is stored and there are no migrations.

## Capabilities

### New Capabilities
- `dream-cycle-history-page`: web page summarising recent dream cycles.

### Modified Capabilities
<!-- none -->

## Impact

- New `zebra-agent-web/zebra_agent_web/api/dream_history.py`, view `dream_cycles` in `web_views.py`, route in `urls.py`.
- Templates: new `pages/dream_cycles.html`; nav entry in `base.html`; `moon` icon in `partials/_nav_link.html`.
