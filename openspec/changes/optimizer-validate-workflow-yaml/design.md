## Context

`workflow_optimizer` was the only workflow generator not covered by `check_generated_workflow` from #122. It saved whatever the LLM returned and always added an entry to `changes_made`, so the dream summary reported broken output as a fix.

## Decisions

- **Reuse the #122 helpers** (`GENERATED_WORKFLOW_MAX_TOKENS`, `check_generated_workflow`) so all generators share one definition of "valid".
- **Retry once on truncation** with twice the token budget. Rewriting a large existing workflow can legitimately need more room. If the retry is also truncated, the change is rejected.
- **Check the action registry only when it is available**: task actions are checked with `context.engine.actions.has_action` when the engine can be reached, and the check is skipped otherwise.
- **Fail each change separately, not the whole task**: one bad rewrite should not throw away valid new workflows from the same run. Rejected changes go into `failed_changes` (`type`, `workflow`, `reason`) and do not count against the `max_changes` budget.
- **Bump `dream_cycle.yaml` to v3** so the library's builtin sync copies the new summary prompt to existing installs.

## Risks

- The retry doubles the worst-case output-token cost when a change is truncated.
- A model whose output cap is below 16000 tokens may reject the retry. The API error is caught and recorded as a failed change.
