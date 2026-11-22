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
- The curator, optimizer and variant creator prompts tell the LLM about the flag so dream-cycle
  edits can use it (the #324 fix is then data: mark the Compute variants `entry_point: false`).
- Docs: `zebra-agent/AGENTS.md` and `specs/zebra-as-is.md`.

## Non-goals

- Alias routing, or a separate `visibility` enum (a boolean covers the need; see design).
- Editing the learned Compute workflows in prod (a dream/curator action after deploy).
- Restricting who may run a workflow by name, or hiding it from the library UI.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | A workflow with `entry_point: false` is never in the selector's candidate list | unit test on `list_goal_workflows`; selector prompt in a test has no such name |
| O2 | A workflow without the key (every existing one) is still offered | unit test; existing selector/library tests pass unchanged |
| O3 | An `entry_point: false` workflow can still be run as a sub-workflow and fetched by name | unit/engine test using `get_workflow` and a subworkflow task |
| O4 | The flag survives `WorkflowLibrary.save()` and a malformed value (non-bool) is rejected or treated as `true` with a warning | unit tests on save round-trip and bad value |
| O5 | Authoring guidance documents the flag | `zebra-agent/AGENTS.md`, `specs/zebra-as-is.md` and the curator prompt mention `entry_point` |
