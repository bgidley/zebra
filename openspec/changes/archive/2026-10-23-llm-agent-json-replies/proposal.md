## Why

In Outcome Review process `7f93a88a` (the #211 review) the `zebra_reconsider` `llm_agent` step stored `{"response": " the", "turns": 0}`. `llm_agent` with `response_format: json` keeps a reply it cannot parse as the raw string, so the junk counted as Zebra's reconsideration: `compare_again` repeated the first comparison and the dispute went straight to a human ruling without Zebra ever reconsidering. Issue #216.

## What Changes

- **`llm_agent` with `response_format: json` checks its final answer** with `parse_llm_json` (fences, JSON in prose, as `complete_json`, #195); it must be an object or array (every JSON prompt asks for an object). Whether an object has the right shape stays with the consumer (`compare_outcome_reviews` treats a missing verdict as disputed).
- **One retry, without tools**: an unusable reply (empty, prose, invalid JSON) is retried once with the `complete_json` JSON-only note; a reply cut off at the token limit is retried with twice `max_tokens` and the "be brief" note.
- **Still unusable → the task fails** with the cause (`describe_failure`: truncated / invalid JSON, attempts) and nothing is written to `output_key`. Junk is never stored as an answer.
- Text replies (`response_format` unset or `text`) are unchanged. The only workflow that combines `llm_agent` with JSON is *Outcome Review* (`zebra_review`, `zebra_reconsider`); a failed step there fails the review, which `zebra-outcome-review.sh` already reports as exit 1 ("review could not run").

## Capabilities

### New Capabilities

### Modified Capabilities
- `llm-agent-tools`: JSON answers are parsed, retried once, and fail the task when unusable.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | A junk JSON reply is retried once instead of stored | Tests: `" the"` (invalid JSON) or `"the"` (a bare JSON string, not an object/array) then valid JSON → the task succeeds with the parsed object in `output_key`; the retry was sent without tools and carried the JSON-only note |
| O2 | A reply that stays junk fails the step with a diagnosable cause | Test: two junk replies → task FAILED, error names invalid JSON, 2 attempts and quotes the start of the reply; `output_key` not set |
| O3 | A reply cut off at the token limit is retried with more room, and fails if it is cut off again | Tests: `finish_reason: length` → retry asks for a larger `max_tokens` with the "be brief" note; truncated twice → FAILED with "reply truncated" |
| O4 | Outcome Review no longer treats junk as a reconsideration, and real disputes still reach a human | Workflow tests: junk from `zebra_reconsider` twice → the review fails without reaching `human_ruling`; valid JSON on retry → `compare_again` uses it; the existing lasting-dispute test still reaches `human_ruling` |
| O5 | Text answers unchanged; docs current | Existing `llm_agent` / outcome-review tests pass with no assertion changes; `response_format` row in `zebra-tasks/AGENTS.md` (`LLMAgentAction`), `specs/llm-agent-tools-design.md` and the LLM / Outcome review rows of `specs/zebra-as-is.md` describe retry-once and fail-with-cause |

## Impact

- Changed: `zebra-tasks/zebra_tasks/llm/agent.py`, `zebra-tasks/tests/test_llm_agent.py`, `zebra-agent/tests/test_outcome_review_workflow.py`, `zebra-tasks/AGENTS.md`, `specs/zebra-as-is.md`.
- No migrations, settings, workflow YAML or API changes.
