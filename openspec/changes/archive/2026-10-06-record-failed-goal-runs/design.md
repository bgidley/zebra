## Context

Since #131 the engine fails a process when a task fails and nothing else is active; routings from a FAILED task never fire. The learning tail of the Agent Main Loop (`assess_and_record` → `ethics_post_review` → `update_conceptual_memory`) therefore only runs for successful goal runs. `assess_and_record` and `update_conceptual_memory` already accept `success` and handle `false`.

## Goals / Non-Goals

**Goals:** failed goal runs are recorded to metrics and memory; the main-loop process still ends FAILED with the child's error so the UI, daemon metrics and `AgentLoop` keep reporting failure.

**Non-Goals:** recording failures that happen before execution (selection/creation/ethics-gate errors) — there is no workflow run to assess; the activity view's orphan handling still covers them. Engine-level "on failure" routing.

## Decisions

- **Opt-in flag, not a behaviour change.** `continue_on_failure` defaults false so `execute_goal_workflow`'s failure contract (#131 spec) holds for other callers. Alternative — always succeed with `success: false` — would silently turn failures into completions wherever the action is used.
- **Fail at the end, not at execution.** A tiny `propagate_failure` action as the terminal task re-raises the failure after learning. The process ends FAILED via the existing #131 rule, with `__error__` = child error and `__failed_task__` = `report_outcome`. Alternative — a handled `next_route` branch — would end COMPLETE and misreport the goal as successful.
- Input/argument validation failures (no workflow name, workflow not found) still fail the task immediately: they are configuration errors, not workflow runs.

## Risks / Trade-offs

- If `ethics_post_review` or `update_conceptual_memory` fail, the process ends FAILED with their error instead of the child's — the run is already recorded by then, so learning is not lost.
- `__failed_task__` for a failed goal is now `report_outcome` rather than `execute_workflow`.
