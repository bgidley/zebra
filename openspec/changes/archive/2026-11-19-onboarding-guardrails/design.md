## Context

Slice S2 of `plan-276-278`, shipped on the same branch as S1 (`onboarding-wizard-shell`).

## Decisions

- **Cap in the client, not the action**: every LLM call with a task context goes through
  `_Recorded`, so the check covers `llm_call`, `llm_agent` and any action using `get_llm`. The
  property is generic (`__cost_cap_usd__`) so other entry points can use it. `spent >= cap`
  refuses: one call may overshoot the cap by its own cost, never more. An unreadable cap is 0.
- **Daily cap via an engine extra** (`__llm_guard__`): zebra-tasks cannot query the ledger, so the
  web injects an async guard. It returns at once for processes without `__onboarding__`, so other
  goals pay no query.
- **Spend** = ledger rows (`LLMSpendModel`) since 00:00 UTC whose process is an onboarding process
  (definitions named in `ONBOARDING_WORKFLOWS`).
- **Rate limits** use the default cache (LocMem): one web process, reset on restart (accepted
  risk). Keys hash the IP. The proxy header is opt-in, because trusting it on a directly
  reachable server would let anyone pick their IP.
- **Expiry** lives in the web onboarding module (it knows the ORM) and is called from the daemon
  tick after the kill-switch guard, throttled to hourly. Plan said `zebra_agent/scheduler/`; the
  web module avoids a new store interface for one query.
- **Redaction** rewrites the formatted message (args folded in). Keys must end in `token` or
  `nonce`, so `tokens_used` and other counts stay readable. Exception tracebacks are not
  rewritten; wizard code never puts a token in an exception message.
