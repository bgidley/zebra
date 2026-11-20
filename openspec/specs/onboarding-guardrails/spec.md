# onboarding-guardrails Specification

## Purpose
TBD - created by archiving change onboarding-guardrails. Update Purpose after archive.

## Requirements

### Requirement: LLM cost caps
Before each recorded LLM call the client SHALL refuse, without calling the provider, a process
whose `__total_cost__` has reached its `__cost_cap_usd__`, and any call the engine's
`__llm_guard__` extra refuses. Onboarding sessions SHALL carry `ONBOARDING_SESSION_COST_CAP_USD`,
and onboarding calls SHALL be refused once today's onboarding spend reaches
`ONBOARDING_DAILY_COST_CAP_USD`.

#### Scenario: Over the session cap
- **WHEN** an onboarding process has spent its cap and makes another LLM call
- **THEN** `LLMCostCapExceeded` is raised and the provider is not called

#### Scenario: Daily cap reached
- **WHEN** onboarding spend today has reached the daily cap
- **THEN** onboarding LLM calls and new sessions are refused

### Requirement: Rate limits
The wizard SHALL allow at most `ONBOARDING_REQUESTS_PER_IP_MINUTE` requests per IP per minute and
`ONBOARDING_SESSIONS_PER_IP_HOUR` new sessions per IP per hour (429 beyond), and at most
`ONBOARDING_MAX_LIVE_SESSIONS` live sessions (503 beyond).

#### Scenario: Sixth session in an hour
- **WHEN** one IP starts its sixth session within an hour
- **THEN** the response is 429 and no process is created

### Requirement: Idle expiry and pause
The daemon tick SHALL fail onboarding sessions without progress for
`ONBOARDING_SESSION_IDLE_DAYS`. While the kill switch is on, the wizard SHALL refuse new sessions
and step submissions.

#### Scenario: Idle session
- **WHEN** a session's process was last updated 31 days ago
- **THEN** the next expiry pass fails it with an "expired" reason

### Requirement: Log redaction
Every log handler SHALL mask onboarding resume paths, the onboarding cookie and values of keys
ending in `token` or `nonce`.

#### Scenario: Resume link in a request log
- **WHEN** a log line holds `/onboarding/r/<token>/`
- **THEN** the handler writes `/onboarding/r/[redacted]/`
