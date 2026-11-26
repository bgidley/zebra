## MODIFIED Requirements

### Requirement: OpenRouter provider
Unless `ZEBRA_LLM_PROVIDER` is `bedrock` (see bedrock-provider), every LLM call SHALL go through
OpenRouter's OpenAI-compatible API using `OPENROUTER_API_KEY`, with the endpoint overridable by
`OPENROUTER_BASE_URL`. `get_llm(model, context)` SHALL be the only way to obtain an LLM. On
OpenRouter, without `OPENROUTER_API_KEY` it SHALL raise a `ValueError` naming it.

#### Scenario: Provider by name
- **WHEN** `get_llm("high")` is called with `OPENROUTER_API_KEY` set and no provider configured
- **THEN** an OpenRouter LLM for the high tier is returned

#### Scenario: Missing key
- **WHEN** `get_llm()` is called on OpenRouter without `OPENROUTER_API_KEY`
- **THEN** a `ValueError` naming `OPENROUTER_API_KEY` is raised

### Requirement: Provider-reported cost
The cost OpenRouter reports for each call SHALL be recorded on the calling task's process
(`__total_cost__`, `__total_tokens__`, `__token_history__`) whenever the LLM was obtained with that
task's context. OpenRouter calls SHALL use no price tables (Bedrock calls are priced from tokens,
see bedrock-provider).

#### Scenario: OpenRouter cost tracked
- **WHEN** an action calls an LLM from `get_llm(model, context)` and OpenRouter reports `usage.cost` 0.0123
- **THEN** `__total_cost__` increases by 0.0123

#### Scenario: No reported cost
- **WHEN** OpenRouter reports no cost
- **THEN** the call is recorded with cost 0
