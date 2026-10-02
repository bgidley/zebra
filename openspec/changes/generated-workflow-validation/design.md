## Context

The engine completes a process when a finished task has no outbound routings; unmatched routings raise `RoutingError`. So a definition that lost its `routings` block runs one task and ends "successfully". `load_definition_from_yaml` only checks referential integrity, not reachability.

## Decisions

- **Detect truncation from `finish_reason`** (`max_tokens` for Anthropic, `length` for OpenAI) rather than heuristics on YAML shape.
- **Reuse `validate_definition`** from `zebra.definitions.loader` to catch orphaned tasks — the exact symptom of a lost routings block.
- **Fail, don't save**: a rejected generation returns `TaskResult.fail` before `library.add_workflow`, so a broken workflow never enters the library or memory.
- **8000-token cap**: room for several JSON-Schema forms; still bounded.

## Risks

- Larger cap raises worst-case cost per creation (~4x output tokens).
- Rejected generations fail the goal rather than retrying; retry is deferred.
