## Context

`WorkflowEvaluatorAction._parse_response` strips a fence only when both the opening and closing
fences are present. A reply cut off at `max_tokens` has no closing fence, so `json.loads` sees
"```json …" and fails. The fallback evaluation keeps the raw text but drops the error and the
`finish_reason`. Prod dream cycles `9e56acce…` (2026-10-17, 7413 chars) and the 2026-10-18 cycle
(9270 chars) both end mid-string. The curator, knowledge review and improvement steps each have
their own parser and also discard the cause.

## Decisions

- **One helper, `zebra_tasks/llm/structured.py`.**
  - `parse_llm_json(content) -> Any`: take the text after an opening fence (and its language
    tag) up to a closing fence or the end; try `json.loads`; then try the span from the first
    `{`/`[` to the last `}`/`]`. Raises `ValueError` with the JSON error.
  - `complete_json(provider, messages, *, temperature, max_tokens, on_response=None) -> Any`:
    makes at most two calls. `on_response(response)` runs after every call, so callers count the
    cost of the retry too.
- **Retry once, with a different prompt.** A truncated reply (`finish_reason` in `max_tokens` /
  `length`) is retried with `max_tokens * 2` and "your reply was cut off, answer again shorter".
  Any other parse failure is retried with "reply with only the JSON object, no prose or fences"
  and the parse error. The note is appended to the last user message rather than added as a new
  turn, so it works with every provider's message ordering.
- **`LLMJSONError(ValueError)`** has a `failure` dict: `error`, `finish_reason`, `truncated`,
  `attempts`, `raw_response`. `raw_response` keeps the first and last 2000 characters, because the
  end shows where a truncated reply stopped. The dict is JSON-serialisable, so it can be stored as
  a process property.
- **Evaluator**: default `max_tokens` 8000 (task property `max_tokens`). On `LLMJSONError` the
  existing fallback shape is kept and gains `parse_failure`; `raw_response` stays for
  compatibility. Key issue: `"Evaluator reply unusable after N attempts: <cause>"`. Cost is
  recorded with `pricing.usage_cost` into `__total_cost__`, like the other dream-cycle steps.
- **Other dream-cycle steps** keep their behaviour on failure (skip, never fail the cycle), but now
  retry and include the cause in the message they record.

## Data model / interfaces

No tables, migrations or YAML changes. The evaluator gains an optional `max_tokens` property and a
`parse_failure` key in its output when parsing fails. `specs/zebra-as-is.md` dream-cycle section:
note the helper.

## Risks

- A retry adds at most one call per step per cycle, and only after a failure.
- A doubled `max_tokens` on a thinking model may still truncate. The failure is then recorded with
  `truncated: true`, which points at the fix.
