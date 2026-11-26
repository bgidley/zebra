# bedrock-provider Specification

## Purpose
AWS Bedrock as an optional LLM provider for the work Zebra (#335): selection, model names, tool use, token-priced cost, credential expiry.

## Requirements

### Requirement: Bedrock provider selection
The system SHALL build LLMs on AWS Bedrock (Converse API) when `ZEBRA_LLM_PROVIDER` is `bedrock`, and on OpenRouter when it is unset, `openrouter` or unknown. A factory set with `set_llm_factory` SHALL take precedence over either.

#### Scenario: Bedrock selected
- **WHEN** `ZEBRA_LLM_PROVIDER=bedrock` and no factory is set
- **THEN** `get_llm("low")` returns a `BedrockLLM`

#### Scenario: Default unchanged
- **WHEN** `ZEBRA_LLM_PROVIDER` is unset
- **THEN** `get_llm` returns an `OpenRouterLLM`

### Requirement: Bedrock model names
On Bedrock a tier SHALL map to `ZEBRA_BEDROCK_MODEL_<TIER>` (default the Anthropic `global.` Haiku / Sonnet / Opus / Opus inference profiles), an exact Bedrock model ID, inference-profile ID or ARN SHALL be sent as given, and an OpenRouter `vendor/model` slug SHALL be read as its tier with a warning.

#### Scenario: Slug from a synced workflow
- **WHEN** a task names `anthropic/claude-opus-5` on Bedrock
- **THEN** the high tier's Bedrock model is used and a warning is logged

### Requirement: Bedrock tool use
The system SHALL send tools as a Converse `toolConfig`, assistant tool calls as `toolUse` blocks and tool results as `toolResult` blocks, and SHALL return `toolUse` blocks in a reply as tool calls.

#### Scenario: Tool call reply
- **WHEN** Bedrock replies with a `toolUse` block
- **THEN** the response has a `ToolCall` with its id, name and input

### Requirement: Bedrock cost
Each Bedrock call SHALL be priced from its input and output tokens with a per-model table that `ZEBRA_BEDROCK_PRICES` can override; a model with no price SHALL be charged the highest known rate. The cost and the Bedrock model ID SHALL be recorded on the process and in the spend ledger.

#### Scenario: Recorded cost
- **WHEN** a recorded call uses 2,000,000 input and 100,000 output tokens on the low tier
- **THEN** `__total_cost__` and the ledger row hold the priced cost and the ledger model is the Bedrock ID

### Requirement: Expired AWS credentials
Missing or expired AWS credentials, or an unusable or expired `ZEBRA_BEDROCK_TOKEN_FILE`, SHALL raise `LLMProviderAuthError` with "AWS session expired — run `aws sso login --profile <profile>`" and notify the owner over the configured webhook / email at most once an hour. A changed token file SHALL be used without a restart.

#### Scenario: Expired session
- **WHEN** Bedrock answers `ExpiredTokenException`
- **THEN** the `llm_call` task fails with the `aws sso login` message and the owner is notified

#### Scenario: Token file rewritten
- **WHEN** the token file's content and mtime change
- **THEN** the next call uses the new credentials
