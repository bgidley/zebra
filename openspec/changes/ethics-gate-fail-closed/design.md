## Context

`EthicsGateAction` parses the LLM's JSON verdict. The `JSONDecodeError` branch returned an approving fallback (`next_route="proceed"`). The truncation that triggered it came from `max_tokens=800`.

## Decisions

- **Reject, not escalate** — the input gate has only `proceed`/`reject` routings; `reject` lands on the terminal `ethics_rejection` task with the reason, and resubmitting re-runs the evaluation. Consistent with TrustGate / `assess_reversibility` fail-closed behaviour.
- **Distinct audit check type** `kantian+unparseable` so operational failures are countable separately from ethical rejections.
- **Cap to 2000** via a module constant `_MAX_RESPONSE_TOKENS`.

## Data model / API changes

None. No new routes, tables or properties; the audit `check_type` gains a new value.

## as-is sections to update

`specs/zebra-as-is.md` §6 Weaknesses — remove the "ethics gate fails open" entry.
