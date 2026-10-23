## MODIFIED Requirements

### Requirement: Timed-out and crashed goals get a postmortem
When an Agent Main Loop process ends FAILED without having run its `write_postmortem` step, the
daemon (and `AgentLoop` for direct runs) SHALL start the *Postmortem* system workflow. Its
trigger SHALL be `timeout` when the process error says it timed out (case-insensitive
"timed out"), and `failure` otherwise. Goals cancelled by the kill switch SHALL NOT get one.

#### Scenario: Goal timeout
- **WHEN** a daemon goal is failed by the goal timeout
- **THEN** a *Postmortem* process runs and stores a postmortem with trigger `timeout` and the timeout error

#### Scenario: Crash before reflecting
- **WHEN** a goal ends FAILED with "Failed to parse LLM response as JSON" before `write_postmortem`
- **THEN** a *Postmortem* process runs and stores a postmortem with trigger `failure` and that error

#### Scenario: Kill switch
- **WHEN** a goal is cancelled by the kill switch
- **THEN** no postmortem is started
