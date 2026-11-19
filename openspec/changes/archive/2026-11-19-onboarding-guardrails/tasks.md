> Branch: `f276/onboarding-wizard-shell` (with S1). Commits `Part of #276`.

## 1. Caps

- [x] 1.1 `zebra_tasks/llm/client.py`: `check_cost_cap`, `COST_CAP_KEY`, `LLM_GUARD_KEY`, `LLMCostCapExceeded`
- [x] 1.2 `onboarding.llm_guard` + `spent_today` (ledger); injected as `__llm_guard__` in `agent_engine`
- [x] 1.3 Session cap property and daily cap at session start

## 2. Limits and expiry

- [x] 2.1 Per-IP request / session limits (cache), live-session cap, `ONBOARDING_CLIENT_IP_HEADER`
- [x] 2.2 `expire_idle_sessions` from the daemon tick (hourly); kill switch pauses the wizard

## 3. Redaction

- [x] 3.1 `logging_filters.RedactSecretsFilter` on every `LOGGING` handler and the structlog handler

## 4. Tests

- [x] 4.1 `zebra-tasks/tests/test_llm_client.py` cap tests; web guard, limits, expiry, redaction tests
