## ADDED Requirements

### Requirement: Unreadable ethics evaluations fail closed
When the ethics gate cannot parse the LLM's evaluation as JSON (including a response truncated by the token limit), it SHALL treat the goal as not approved: output `approved: false`, route `reject`, and include a concern advising the user to resubmit. It MUST NOT route `proceed`. The audit entry MUST record `approved = false` with `check_type = "kantian+unparseable"`.

#### Scenario: Truncated response is rejected
- **WHEN** the LLM response is cut off mid-JSON and cannot be parsed
- **THEN** the gate routes `reject` with `approved: false`

#### Scenario: Unparseable evaluation is audited as not approved
- **WHEN** the gate cannot parse the evaluation and an audit store is present
- **THEN** one audit entry is written with `approved = false`, `check_type = "kantian+unparseable"` and the task's `user_id`

### Requirement: Ethics evaluation has sufficient response headroom
The ethics gate SHALL request at least 2000 output tokens so the combined Kantian, values and dilemma assessment is not truncated.

#### Scenario: Token cap
- **WHEN** the gate calls the LLM provider
- **THEN** `max_tokens` is at least 2000
