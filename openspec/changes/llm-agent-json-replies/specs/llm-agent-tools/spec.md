## ADDED Requirements

### Requirement: JSON answers are checked
An `llm_agent` task with `response_format: json` SHALL parse its final answer leniently (code fences, JSON in prose) and SHALL accept only a JSON object or array. When the answer cannot be parsed, or is a bare string or number, it SHALL ask once more without tools, appending a JSON-only instruction, or, when the reply was cut off at the token limit, a request to be brief with twice `max_tokens`. When the second answer cannot be parsed either the task SHALL fail with the cause and SHALL NOT write `output_key`. Text answers are unchanged.

#### Scenario: Junk answer is retried
- **WHEN** the model's final answer is `" the"` and its retry is a valid JSON object
- **THEN** the task succeeds with the parsed object in `output_key`, and the retry was sent with no tools and a JSON-only instruction

#### Scenario: Answer that stays junk fails the task
- **WHEN** the final answer and the retry both cannot be parsed as JSON
- **THEN** the task fails with an error naming invalid JSON and 2 attempts and quoting the start of the reply, and `output_key` is not set

#### Scenario: Bare JSON value is not an answer
- **WHEN** the final answer is the JSON string `"the"` and its retry is a valid JSON object
- **THEN** the retry note says an object was expected, and the task stores the object

#### Scenario: Truncated twice fails
- **WHEN** the final answer and its retry are both cut off at the token limit
- **THEN** the task fails with an error naming the truncation and 2 attempts

#### Scenario: Truncated answer gets more room
- **WHEN** the final answer cannot be parsed and its `finish_reason` is `length`
- **THEN** the retry asks for twice `max_tokens` and to keep the answer brief

#### Scenario: Text answers unchanged
- **WHEN** `response_format` is not `json`
- **THEN** the final answer is stored as text without a retry
