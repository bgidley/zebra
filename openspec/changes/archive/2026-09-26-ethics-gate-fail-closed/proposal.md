## Why

In prod (2026-09-26) the ethics gate's LLM response was cut off at the `max_tokens=800` cap, the truncated JSON failed to parse, and the gate **approved by default** — routing `proceed` and writing an *approved* entry to the ethics audit. A safety gate that approves whenever its own evaluation is unreadable is not a gate. Every other ethics-gate error path already fails the task, and the trust gate and reversibility assessor fail closed. Closes #118.

## What Changes

- An unparseable ethics evaluation now **fails closed**: `approved: false`, route `reject`, with a concern telling the user to resubmit.
- The audit records it as not approved with `check_type = "kantian+unparseable"` (and the real `user_id`), so these are distinguishable from considered rejections.
- The response cap rises from 800 to 2000 tokens so the Kantian + values + dilemma JSON is not truncated in the first place.

## Capabilities

### New Capabilities
<!-- None -->

### Modified Capabilities
- `ethics-gate-values-integration`: adds a fail-closed requirement for unreadable evaluations.

## Non-goals

- Escalating unreadable evaluations to a human: `escalate` is only wired from `ethics_plan_review`, and the dilemma-resolution "proceed" path skips planning, so input-gate escalation needs its own routing — deferred.
- Automatic retry of the LLM call.
- Changing `ethics_post_review` (a non-gating `llm_call`).

## Impact

- `zebra-tasks/zebra_tasks/agent/ethics_gate.py`, `zebra-tasks/tests/test_ethics_gate.py`.
- Behaviour: goals whose evaluation cannot be parsed are rejected instead of run; the user resubmits.
