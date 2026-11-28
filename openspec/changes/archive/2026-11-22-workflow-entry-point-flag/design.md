## Context

`list_goal_workflows` (`zebra_agent/library.py`) is the single builder of selector candidates; it
already excludes `system`-tagged and tool-only workflows (#146). Every goal entry point uses it.
Sub-workflow and tool calls resolve by name through `WorkflowLibrary.get_workflow`, not through
that list.

## Decisions

- **Boolean `entry_point`, default true**, read in `_load_workflow_info` next to `use_when`.
  Simpler than `visibility: internal|private` and matches the issue's alternative wording. Missing
  key means true, so no migration and no version bump for existing files.
- **Filter in `list_goal_workflows` only**, via `is_tool_only`-style helper `is_entry_point(info)`.
  Execution paths are untouched, which keeps dispatcher → variant sub-workflow calls working.
- **Strict parse**: only a real YAML `false` hides a workflow; strings such as `"false"` are
  logged as a warning and treated as `true`, so a typo never silently hides a workflow.
- **Provenance**: `save()` writes the YAML as given, so the key round-trips; no `commons` block
  change. An import from Commons keeps the key (it is part of the workflow, not trust metadata).
- **Authoring**: curator/optimizer/variant-creator prompts mention the flag so variants of a
  dispatcher can be hidden by the dream cycle.

## Risks

- A hidden workflow with no dispatcher calling it becomes unreachable by goals. Mitigation: it
  remains listed in the library UI and runnable by name; document in AGENTS.md.
- Metrics for hidden variants still accrue via sub-workflow runs; unchanged.
