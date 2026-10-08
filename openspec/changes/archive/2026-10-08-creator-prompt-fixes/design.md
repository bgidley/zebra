## Context

Issue #139. `WorkflowCreatorAction` assembles header + registry action list + footer as the system prompt. `ExecuteWorkflowAction._extract_output` reads `definition.properties["result_key"]`, but `load_definition_from_yaml` only copies the YAML `properties:` block, so the documented top-level `result_key` (used by the prompt and `web_search.yaml`) was silently ignored.

## Decisions

- **Fix `result_key` in the loader, not the prompt.** Top-level is what the prompt, `web_search.yaml` and LLM output already use; making the loader honour it fixes every existing generated workflow in the library too. `properties.result_key` takes precedence if both are set.
- **One repair round, not a loop.** On YAML parse or `validate_definition` failure, resend the conversation with the bad YAML as the assistant turn and the error as the user turn. If the repair also fails, fail as before. Truncation is not repaired (the budget is already 8000 tokens; the spec requires failing).
- **Temperature 0.3.** Output is structured YAML; creativity belongs in the generated workflow's own `llm_call` tasks.
- **Prompt states engine facts, not style.** Every new prompt line maps to engine behaviour: serial routings stop at the first that fires (`engine.py` routing loop); `route_name` is only set by `next_route` (human form buttons via `get_routes_from_definition`); `llm_call` stores its response text under `output_key`.

## Risks

- Repair doubles LLM cost on failure paths only.
- The optimizer keeps its own prompt copy; unifying them is out of scope.
