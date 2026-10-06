## Why

The three places that queue or start an Agent Main Loop goal each build the selector's `available_workflows` list their own way. `AgentLoop.process_goal()` (CLI, `run_goal`, API view) excludes a hard-coded set of 5 names, so `system`-tagged workflows such as "Knowledge Decay" and "File Operations" leak into the selector. The web/daemon queue path (`api/goals.py`) and the `queue_goal` action filter on the `system` tag but format `success_rate` as a string. `api/goals.py` also hard-codes the LLM provider. Queued goals snapshot the list at queue time, so they miss workflows created before the daemon runs them. Issue #144.

## What Changes

- New `zebra_agent.library.list_goal_workflows(library)`: the single source of the selector's workflow list (excludes `system`-tagged workflows, `success_rate` as a float).
- `AgentLoop.process_goal`, `api/goals.queue_goal` and the `queue_goal` task action all use it; `AgentLoop._is_system_workflow` is removed.
- `workflow_selector` refreshes the list from the live library (`__workflow_library__` extra) at selection time, falling back to the `available_workflows` property, so a queued goal sees the current library.
- The selector shows "N/A" success for never-run workflows (was "0%" on the direct path).
- `api/goals.queue_goal` uses the configured `LLM_PROVIDER` instead of `"anthropic"`.
- Cleanups: drop the stale "memory compaction check" docstrings in `loop.py`; drop `synchronized: true` from `flag_concerns` in `agent_main_loop.yaml` (no parallel inbound branches).

## Capabilities

### New Capabilities
- `goal-workflow-list`: how the workflow candidates offered to the selector are built and refreshed.

### Modified Capabilities
<!-- none -->

## Impact

- `zebra-agent/zebra_agent/library.py`, `zebra-agent/zebra_agent/loop.py`, `zebra-agent/workflows/agent_main_loop.yaml`
- `zebra-agent-web/zebra_agent_web/api/goals.py`
- `zebra-tasks/zebra_tasks/agent/queue_goal.py`, `zebra-tasks/zebra_tasks/agent/selector.py`
- Behaviour change: the direct path no longer offers `system`-tagged workflows. `AgentLoop._is_system_workflow` (private) is removed.
