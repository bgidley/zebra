## Context

Continuations (F116/F134/F135) carry `previous_run_context` — a compact summary built from the metrics store — and `with_previous_run()` appends it to the child's `goal`. Task-execution outputs in the metrics store are capped at 500 chars, so the full values a workflow wrote (e.g. *Web Research*'s `research_brief`) only exist on the previous goal-workflow process. #187 already finds that process for failed retries (`ExecuteGoalWorkflowAction._previous_child`).

## Decisions

- **Source: the previous goal-workflow process.** Not the metrics store (truncated) and not a new run→process column (needs a migration). `_previous_child` gains a `states` argument, so one lookup serves #187 (failed only) and #222 (failed or completed, newest first).
- **One dict, `prior_outputs`.** Templates already dig into dicts (`{{prior_outputs.research_brief}}`), and an absent property resolves to `""`, so workflows need no conditionals. A single key keeps the child's namespace clean and avoids clobbering its own outputs.
- **`from_prior` is opt-in per input.** Name-matching inputs to prior keys automatically would also carry stale `refinements`/`context`. An explicit keyword on the input schema is visible in the YAML and ignored by JSON Schema consumers (`llm_agent` tool parameters).
- **Caps** (`MAX_PRIOR_VALUE_CHARS` 8000, `MAX_PRIOR_OUTPUTS_CHARS` 32000, in characters of the string or of the value's JSON) keep process properties small on Oracle. A long string is cut (a cut brief is still useful); any other large value is dropped, since cut JSON is not data. Search-result lists usually drop, briefs and summaries stay.

## Risks

- The lookup scans terminal root processes (as #187 does). Fine at current volume; a run→process link would be the fix if it gets slow.
- Prod's *Web Research* only benefits once its `prior_brief` input declares `from_prior: research_brief`; that is a library edit, not part of this change.
