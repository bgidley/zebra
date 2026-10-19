# openrouter-provider Specification

## Purpose
TBD - created by archiving change openrouter-provider. Update Purpose after archive.

## Requirements

### Requirement: OpenRouter provider
Every LLM call SHALL go through OpenRouter's OpenAI-compatible API using `OPENROUTER_API_KEY`,
with the endpoint overridable by `OPENROUTER_BASE_URL`. `get_llm(model, context)` SHALL be the
only way to obtain an LLM. Without `OPENROUTER_API_KEY` it SHALL raise a `ValueError` naming it.

#### Scenario: Provider by name
- **WHEN** `get_llm("high")` is called with `OPENROUTER_API_KEY` set
- **THEN** an OpenRouter LLM for the high tier is returned

#### Scenario: Missing key
- **WHEN** `get_llm()` is called without `OPENROUTER_API_KEY`
- **THEN** a `ValueError` naming `OPENROUTER_API_KEY` is raised

### Requirement: Provider-reported cost
The cost OpenRouter reports for each call SHALL be recorded on the calling task's process
(`__total_cost__`, `__total_tokens__`, `__token_history__`) whenever the LLM was obtained with that
task's context. There SHALL be no price tables.

#### Scenario: OpenRouter cost tracked
- **WHEN** an action calls an LLM from `get_llm(model, context)` and OpenRouter reports `usage.cost` 0.0123
- **THEN** `__total_cost__` increases by 0.0123

#### Scenario: No reported cost
- **WHEN** OpenRouter reports no cost
- **THEN** the call is recorded with cost 0

### Requirement: Model tiers
Zebra SHALL name models by cost tier: `low`, `medium`, `high`, `max` (default `medium`). A tier
SHALL be sent to `openrouter/auto` with the auto-router plugin's `cost_tier` set to the tier. A
`vendor/model` slug SHALL be sent as given, without the plugin. Names stored before tiers
(`haiku`, `sonnet`, `opus`, `claude-*`) SHALL be read as low, medium and high.

#### Scenario: Tier request
- **WHEN** an LLM for `low` completes a prompt
- **THEN** the request uses model `openrouter/auto` with `plugins: [{id: auto-router, cost_tier: low}]`

#### Scenario: Exact model
- **WHEN** an LLM for `moonshotai/kimi-k3` completes a prompt
- **THEN** the request uses model `moonshotai/kimi-k3` with no auto-router plugin

#### Scenario: Legacy name
- **WHEN** a process stored with `__llm_model__` `sonnet` calls an LLM
- **THEN** the medium tier is used

### Requirement: Reasoning headroom
Every request SHALL add 4096 tokens to the caller's `max_tokens`, so a reasoning model does not
spend a small budget on thinking and return an empty answer.

#### Scenario: Small budget
- **WHEN** a step asks for 500 tokens
- **THEN** the request's `max_tokens` is 4596
