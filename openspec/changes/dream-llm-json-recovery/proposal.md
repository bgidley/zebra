## Why

Both dream cycles since #189 (2026-10-17, 2026-10-18) lost their whole evaluation: the
`workflow_evaluator` reply was cut off at the token limit. The parser needs a closing code fence, so
the cycle recorded only `"Response parsing failed"`, with no error or `finish_reason`. Zebra raised
this as an improvement request, which was accepted. Closes #195.

## What Changes

- New helper `zebra_tasks.llm.structured`:
  - `parse_llm_json()` accepts an unclosed fence and JSON inside prose.
  - `complete_json()` retries an unparseable reply once: with twice the token budget if it was
    truncated, else with a JSON-only instruction. A second failure raises `LLMJSONError` holding
    the error, `finish_reason`, truncation flag, attempts and the capped raw reply.
- `workflow_evaluator` uses it, with default `max_tokens` 8000. On failure it stores
  `parse_failure` and its key issue names the cause. It now adds its cost to `__total_cost__`.
- The curator's duplicate check, knowledge review and improvement proposals use it too and record
  the cause.

## Capabilities

### New Capabilities
- `llm-json-recovery`: parse structured LLM replies leniently, retry once, and record why a reply
  could not be used.

### Modified Capabilities
<!-- none -->

## Impact

- `zebra-tasks`: new `llm/structured.py`; `agent/evaluator.py`, `agent/curator.py`,
  `knowledge/review.py`, `agent/improvements.py`.
- No data model, migration or workflow YAML changes.

## Non-goals

- Provider-native structured output (tool or schema-constrained) is left for later.
- Moving parsers outside the dream cycle (`llm_call`, `assess_stuck`, `extract_knowledge`) onto
  the helper.
- Showing `parse_failure` on `/dreams/`: the key issue carries the cause, and the trace page shows
  the full record.

## Outcomes

| # | Outcome | How we'll know |
|---|---|---|
| O1 | An evaluator reply truncated at the token limit is retried once with twice `max_tokens` and a brevity note, and the retry's JSON becomes the full evaluation. JSON in prose or an unclosed fence parses without a retry | Fake-LLM tests: `finish_reason` `max_tokens` then valid JSON → 2 calls, budgets `[8000, 16000]`, no `parse_failure`; prose / unclosed fence → 1 call. Smoke: next prod dream cycle's `evaluation` has no `parse_failure` |
| O2 | When the retry also fails, the task still succeeds and `evaluation.parse_failure` holds `error`, `finish_reason`, `truncated`, `attempts` and `raw_response` (start + end, ≤ 4000 chars), and the key issue names the cause. Provider errors are not retried here (the SDK already retries) | Fake-LLM test failing twice; helper test on the cap |
| O3 | Knowledge review (`knowledge_review.errors`), improvement proposals (`improvement_requests.errors`) and the curator's duplicate check (warning log) use the same helper, retry once, and name the cause | Shared helper tests; one test per action for retry and cause |
| O4 | The dream cycle's `__total_cost__` includes every evaluator call, retry included | Fake-LLM test: `__total_cost__` = start + sum of each call's cost |
