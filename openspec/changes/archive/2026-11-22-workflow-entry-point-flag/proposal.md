## Why

Overlapping workflow variants compete in the selector on `use_when` text alone. In #324 four
Compute workflows plus a correctness check are all candidates; the designated *Compute Risk
Dispatcher* has 0 runs, so editing descriptions cannot make routing reliable. A workflow that is
only meant to be a sub-workflow of another needs a way to say "never route a goal to me".

## What Changes

- Workflow YAML gains an optional top-level `entry_point: bool` (default `true`).
- `list_goal_workflows` drops workflows with `entry_point: false`, like `system` and tool-only
  ones, so the selector, `queue_goal` and the agent loop never offer them.
- `WorkflowInfo` carries `entry_point`; `get_workflow`, subworkflow calls and tool calls by name are
  unchanged, so a non-entry-point workflow stays callable from a dispatcher.
- `WorkflowInfo.to_dict()` and `WorkflowInfoSerializer` expose the flag. The #324 fix is then data: mark the Compute variants `entry_point: false`.
- Docs: `zebra-agent/AGENTS.md` and `specs/zebra-as-is.md`.
- Non-goal: curator/optimizer/variant-creator prompt edits (no workflow sets the flag yet).

## Non-goals

- Alias routing, or a separate `visibility` enum (a boolean covers the need; see design).
- Editing the learned Compute workflows in prod (a dream/curator action after deploy).
- Restricting who may run a workflow by name, or hiding it from the library UI.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | A workflow with `entry_point: false` is absent from `list_goal_workflows` (the source of `available_workflows`) | unit test on `list_goal_workflows` output |
| O2 | A workflow without the key, or with `true`, is still offered | unit tests |
| O3 | A hidden workflow is still in `list_workflows()` and loadable by `get_workflow(name)` | unit tests |
| O4 | A non-bool value logs a warning and is treated as `true` (workflow not dropped) | unit test asserting the warning |
| O5 | The flag is read from a saved file and exposed by `WorkflowInfo.to_dict()` and `WorkflowInfoSerializer` | save/`get_workflow_info` round-trip test; serializer field |
