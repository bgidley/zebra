## Why

The dashboard only lists *completed* runs (from metrics). Goals that are executing right now — or
stalled waiting on a human task — are invisible there; you have to open `/activity/` to see them.
Issue #126.

## What Changes

- New **Running Activities** panel on the dashboard listing top-level goals whose process is
  `RUNNING`, with goal text, workflow, elapsed time, cost so far, and tasks currently in flight
  across the whole process tree (root + sub-processes).
- Goals blocked on a human (`auto: false`) task are flagged "awaiting input" and link to the task form.
- New **Running** stat card (count) linking to `/activity/`.
- Empty state "Nothing running".

## Capabilities

### New Capabilities

- `dashboard-running-activities`: dashboard summary of in-flight goals.

### Modified Capabilities

_(none)_

## Non-goals

- No live auto-refresh (page reload shows current state); can follow later via HTMX polling.
- No cancel/actions from the dashboard — `/activity/` remains the place to manage processes.
