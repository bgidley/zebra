## Why

When a goal's workflow fails, the Agent Main Loop records the failure and ends FAILED (#140). The
user finds out after the fact, and Zebra never gets the one thing that would unstick it: a
human's hint. Zebra itself asked for "a graceful way to ask a human for help instead of flailing
or silently failing". Issue #176.

## What Changes

- New `assess_stuck` step after `execute_workflow`. A failed goal run, while the help budget lasts
  (`max_help_requests`, default 2), is parked on a human task instead of failing. A cheap haiku
  call writes the help request in Zebra's voice: what I tried, where I'm stuck, what I need.
  Without an LLM, a plain request is built from the error.
- New human task `stuck_help_request`: the user chooses **retry** (optional guidance), **redirect**
  (a new goal) or **abandon**.
- New `apply_help_response` step routes on that choice: retry re-runs the same workflow with the
  guidance added to the goal; redirect replaces the goal and goes back through the ethics input
  gate and workflow selection; abandon carries on to today's record-then-fail path.
- Successful runs, and failed runs once the help budget is spent, behave exactly as before.

## Capabilities

### New Capabilities
- `stuck-handoff`: park a failed goal on a help request to a human and resume with their answer.

### Modified Capabilities
<!-- none -->

## Impact

- `zebra-tasks/zebra_tasks/agent/stuck.py` (new actions + `with_help_guidance`), entry points.
- `execute_goal_workflow` appends retry/redirect guidance to the child's goal.
- `zebra-agent/workflows/agent_main_loop.yaml` (version 16).
- No data model or migration changes; state lives in process properties.
