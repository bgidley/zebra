# llm-json-recovery Specification

## Purpose
Dream-cycle steps that ask an LLM for JSON parse the reply leniently, retry an unusable reply
once, and record why a reply could not be used instead of a bare "parsing failed" (#195).

## Requirements

### Requirement: Lenient JSON extraction from LLM replies
The system SHALL extract a JSON value from an LLM reply that wraps it in a code fence (with or
without a closing fence) or in surrounding prose.

#### Scenario: Fence without a closing fence
- **WHEN** a reply is "```json" followed by a complete JSON object and no closing fence
- **THEN** the object is parsed

#### Scenario: JSON inside prose
- **WHEN** a reply has text before and after a JSON object
- **THEN** the object is parsed

### Requirement: One retry for an unusable structured reply
`complete_json` SHALL retry once when a reply cannot be parsed. A truncated reply SHALL be retried
with twice the token budget, and any other parse failure with a JSON-only instruction. Every call's
response SHALL be passed to the caller's callback so its cost is counted.

#### Scenario: Truncated reply then a complete one
- **WHEN** the first reply has `finish_reason` `max_tokens` and does not parse, and the second
  parses
- **THEN** the parsed second reply is returned, the second call used twice the `max_tokens`, and
  the callback ran twice

#### Scenario: Prose reply then valid JSON
- **WHEN** the first reply is not JSON and was not truncated, and the second is valid JSON
- **THEN** the second call's user message asks for only the JSON object and the parsed reply is
  returned

#### Scenario: Both attempts fail
- **WHEN** neither reply parses
- **THEN** `LLMJSONError` is raised with `failure` holding `error`, `finish_reason`, `truncated`,
  `attempts` = 2 and the capped `raw_response`

### Requirement: Dream-cycle evaluation records why it failed
The workflow evaluator SHALL use `complete_json`. When no usable reply is obtained, it SHALL keep
the fallback evaluation, store the failure under `parse_failure`, and name the cause in
`overall_assessment.key_issues`. It SHALL add every call's cost to `__total_cost__`.

#### Scenario: Evaluation succeeds on retry
- **WHEN** the first evaluator reply is truncated and the retry is valid JSON
- **THEN** the stored evaluation is the parsed reply, with no `parse_failure`

#### Scenario: Evaluation fails twice
- **WHEN** both evaluator replies are truncated
- **THEN** the evaluation has `parse_failure.truncated` true and a key issue saying the reply was
  truncated at the token limit, and the task still succeeds

#### Scenario: Cost is counted
- **WHEN** the evaluator makes an LLM call
- **THEN** `__total_cost__` increases by that call's cost

### Requirement: Other dream-cycle steps share the recovery
The curator's duplicate check, knowledge review and improvement proposals SHALL use
`complete_json` and SHALL record the failure cause when no usable reply is obtained, without
failing the dream cycle.

#### Scenario: Improvement proposals reply unusable twice
- **WHEN** both replies to the improvement step are not JSON
- **THEN** no request is started and the step's errors include the parse cause
