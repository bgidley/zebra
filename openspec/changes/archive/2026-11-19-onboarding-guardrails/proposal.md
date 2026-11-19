## Why

#276 S2 (`specs/onboarding-design.md`, threat model T1/T2): the anonymous wizard must not let a
bot burn the host's LLM budget, flood it with sessions, keep sessions forever, or leak resume
tokens into logs.

## What Changes

- **LLM cost cap** (generic): `zebra_tasks.llm.client` checks, before every recorded call, the
  process's `__cost_cap_usd__` against its `__total_cost__`, then the optional `__llm_guard__`
  engine extra; a refusal raises `LLMCostCapExceeded` and spends nothing. Onboarding sessions get
  `__cost_cap_usd__ = ONBOARDING_SESSION_COST_CAP_USD` (0.05). The web injects
  `onboarding.llm_guard`, which refuses onboarding calls once today's onboarding spend (ledger)
  reaches `ONBOARDING_DAILY_COST_CAP_USD` (1.00); new sessions are refused then too.
- **Rate limits** (Django cache): 60 wizard requests/minute and 5 new sessions/hour per IP, 200
  live sessions overall; 429 / 503. `ONBOARDING_CLIENT_IP_HEADER` names a trusted proxy header
  (`CF-Connecting-IP` behind the Cloudflare Tunnel), else `REMOTE_ADDR`.
- **Idle expiry**: each daemon tick (at most hourly) fails onboarding sessions with no progress for
  `ONBOARDING_SESSION_IDLE_DAYS` (30). Tokens expire after the same time from the last visit.
- **Kill switch** pauses the wizard: no new sessions or step submissions (503).
- **Log redaction**: `logging_filters.RedactSecretsFilter` on every handler masks
  `/onboarding/r/<token>`, the `zebra_onboarding` cookie and `*token=` / `*nonce=` values.

## Capabilities

### New Capabilities
- `onboarding-guardrails`: cost caps, rate limits, expiry and redaction for the wizard.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | A session over its cap (or over the daily onboarding cap) fails its LLM call without calling the provider or spending | `test_a_session_over_its_cap_fails_its_llm_call_without_spending`, `zebra-tasks/tests/test_llm_client.py` cap tests |
| O2 | The 6th new session from one IP within an hour gets 429; another IP still starts | `test_the_sixth_session_from_one_ip_in_an_hour_gets_429` |
| O3 | Sessions idle past 30 days are failed by the daemon tick; active ones stay | `test_idle_sessions_expire_and_active_ones_stay`, `test_the_daemon_tick_expires_idle_sessions` |
| O4 | No resume token or nonce reaches a log line | `test_onboarding_token.py` redaction tests |
