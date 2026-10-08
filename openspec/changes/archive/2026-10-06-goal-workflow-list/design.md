## Context

`available_workflows` is set as a process property when a goal is created and read by `workflow_selector` (and passed to `workflow_creator` as `existing_workflows`). Three builders existed with different filters and formats (#144).

## Decisions

**Filter on the `system` tag, not names.** Workflow YAML already tags internal workflows `system`; the hard-coded name set in `loop.py` was a stale subset. Tags are the one rule all three builders agree on going forward.

**Module function over a `WorkflowLibrary` method.** `list_goal_workflows(library)` wraps `library.list_workflows()`, so the many tests and callers that stub `list_workflows` keep working, and `zebra-tasks` uses it through a lazy import (as other agent actions already do).

**`success_rate` as a float.** It matches `WorkflowInfo` and the selector's documented input; the selector renders "N/A" when `use_count` is 0 rather than relying on a pre-formatted string.

**Refresh at selection time.** The selector prefers the live library from `context.extras["__workflow_library__"]` and falls back to the property, which stays for the creator, the run view and processes without the extra. A refresh failure is logged and falls back; it never fails selection.

## Risks

- The selector now does a library scan (YAML files + one stats query) per goal. It already did this at queue time; the cost moves rather than doubles for queued goals, and is small.
