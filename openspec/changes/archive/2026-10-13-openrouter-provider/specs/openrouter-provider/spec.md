## ADDED Requirements

### Requirement: OpenRouter provider
The system SHALL provide an `openrouter` LLM provider that calls OpenRouter's OpenAI-compatible
API using `OPENROUTER_API_KEY`, with the endpoint overridable by `OPENROUTER_BASE_URL`.

#### Scenario: Provider by name
- **WHEN** `get_provider("openrouter")` is called with `OPENROUTER_API_KEY` set
- **THEN** an OpenRouter provider is returned

#### Scenario: Missing key
- **WHEN** `get_provider("openrouter")` is called without `OPENROUTER_API_KEY`
- **THEN** a `ValueError` naming `OPENROUTER_API_KEY` is raised

### Requirement: OpenRouter model resolution
The provider SHALL map `haiku`, `sonnet` and `opus` (and their Anthropic model ids) to the
matching `anthropic/claude-*-5.5` slug, pass `vendor/model` slugs through unchanged, and use
`OPENROUTER_MODEL` (default `anthropic/claude-sonnet-5.5`) for any other name.

#### Scenario: Tier name
- **WHEN** the provider is created with model `haiku`
- **THEN** requests use `anthropic/claude-haiku-5.5`

#### Scenario: Raw slug
- **WHEN** the provider is created with model `moonshotai/kimi-k3`
- **THEN** requests use `moonshotai/kimi-k3`

#### Scenario: Unknown name
- **WHEN** the provider is created with model `openrouter` and `OPENROUTER_MODEL` is unset
- **THEN** requests use `anthropic/claude-sonnet-5.5`

### Requirement: Provider-reported cost
When a provider reports a call's USD cost, cost tracking SHALL use that cost instead of the
price tables.

#### Scenario: OpenRouter cost tracked
- **WHEN** an `llm_call` task runs on OpenRouter and the response reports `usage.cost` 0.0123
- **THEN** `__total_cost__` increases by 0.0123

#### Scenario: No reported cost
- **WHEN** a provider reports no cost
- **THEN** the cost is calculated from the price tables as before

### Requirement: CLI model choice
`zebra goal` and `manage.py run_goal` SHALL accept `--model openrouter`, which runs the goal on
the `openrouter` provider.

#### Scenario: CLI selects OpenRouter
- **WHEN** `zebra goal "..." --model openrouter` is run
- **THEN** the goal runs with provider `openrouter`
