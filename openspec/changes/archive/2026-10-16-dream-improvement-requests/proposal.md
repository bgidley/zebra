## Why

The dream cycle can change workflows (YAML) but cannot ask for changes to Zebra itself. Problems that need engine, task-action or UI work — evaluator key issues, continuation capability gaps, optimizer changes rejected because an action does not exist — only reach a human as free text in the dream summary. GitLab issue #189 (related: #98 code self-improvement, #186 bug reports).

## What Changes

- New `propose_zebra_improvements` task action (`zebra_tasks/agent/improvements.py`), run in `dream_cycle.yaml` v7 after `review_knowledge`, before the summary.
- One LLM call (haiku by default) reads the cycle's evaluation (key issues, priorities), continuation capability gaps and the optimizer's rejected changes, plus the titles of earlier requests, and returns only problems that need a change to Zebra's code (not a workflow edit). Capped at `max_requests` (default 2) per cycle; duplicates of earlier requests (by normalised title) are dropped.
- Each request starts a *Zebra Improvement Request* process (`zebra-agent/workflows/zebra_improvement_request.yaml`, system workflow): one human task to accept / reject / mark duplicate / defer, with an optional GitLab issue link and notes. It appears in the normal human-task inbox.
- `/dreams/` lists recent improvement requests with their status and a Review link; each cycle shows how many it requested.
- Summary gets an "Improvements requested" section.
- The step never fails the cycle: missing provider, library or bad LLM output → empty result with an error noted.

Not in scope: creating GitLab issues automatically (needs a GitLab token in prod — follow-up), or Zebra editing its own code (#98).

## Capabilities

### New Capabilities
- `dream-improvement-requests`: dream-cycle requests for improvements to Zebra itself, reviewed by a human.

### Modified Capabilities
<!-- none -->

## Impact

- `zebra-tasks/zebra_tasks/agent/improvements.py` (new), `zebra-tasks/pyproject.toml` entry point
- `zebra-agent/workflows/dream_cycle.yaml` v7, `zebra-agent/workflows/zebra_improvement_request.yaml` (new)
- `zebra-agent-web/zebra_agent_web/api/dream_history.py`, `api/web_views.py`, `templates/pages/dream_cycles.html`
- Tests in `zebra-tasks/tests/`, `zebra-agent/tests/test_dream_cycle_workflow.py`, `zebra-agent-web/tests/unit/test_dream_cycles_page.py`
