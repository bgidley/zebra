## Context

`LLMAgentAction._finish` passes the final text to `LLMCallAction._process_response`, which returns the raw string when JSON parsing fails. `complete_json` (#195) already has the retry policy we want, but it calls the provider itself; `llm_agent` owns a multi-turn conversation with tools, so it cannot just call `complete_json`.

## Decisions

- **Reuse, don't duplicate, the policy**: use `parse_llm_json`, the `TRUNCATED_RETRY_NOTE` / `INVALID_RETRY_NOTE` notes, `TRUNCATED_FINISH_REASONS` and `describe_failure` from `structured.py`. The retry appends the junk reply as an assistant message and the note as a user message, then calls once with **no tools** (like `answer_on_budget`, #191) so the retry cannot start another tool loop.
- **Fail, don't fall back**: a second unusable reply fails the task. For Outcome Review this is the honest result: Zebra did not review or reconsider, so the delivering session must see "review could not run" rather than a ruling request built on nothing.
- **Parsed value is stored**: `output_key` gets the parsed JSON (as before when parsing worked).

## Risks

- A model that keeps answering in prose now fails the review instead of escalating. That is intended (#216); the retry makes it rare.
