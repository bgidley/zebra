## Context

`EthicsGateAction` (`zebra-tasks/zebra_tasks/agent/ethics_gate.py`) currently does a single LLM call with a pure Kantian system prompt. It has no knowledge of who is running the workflow or what their personal values are. The values-profile system (ProfileStore, `LoadValuesProfileAction`, `ValuesProfileVersion`) already exists and is accessible via `context.extras["__profile_store__"]`.

## Goals / Non-Goals

**Goals:**
- Allow `EthicsGateAction` to optionally load the user's values profile and fold it into the evaluation.
- Enforce Kantian precedence: a Kantian rejection always wins; values-based rejection blocks a Kantian-approved goal.
- Surface both Kantian and values reasoning in the stored assessment and log output.

**Non-Goals:**
- A new separate "values evaluator" task action.
- Storing values assessments independently of the existing `ethics_assessment` process property.
- Changing the values-profile wizard, `ProfileStore` schema, or database.

## Decisions

### Single combined LLM call (over two sequential calls)

One call with an extended system prompt is simpler, cheaper, and keeps latency low. The LLM already handles nuanced multi-criteria reasoning; asking it to apply Kantian tests and values alignment in the same evaluation is well within its capability. Two separate calls would double cost and add complexity without clear benefit.

### Optional user_id input (backward-compatible)

`user_id` is added as an **optional** input to `EthicsGateAction`. When absent (or when `__profile_store__` is not in `context.extras`), the action behaves exactly as today — Kantian-only. This preserves all existing workflow YAML files without modification.

### Profile loading inside the action (over a prerequisite workflow task)

Having `EthicsGateAction` call `profile_store.get_current(user_id)` directly keeps the gate self-contained. Requiring a preceding `load_values_profile` task would force every workflow that uses the gate to add an extra task and pass the profile through process properties — more fragile and more boilerplate.

### Precedence rule: Kantian rejection wins ties; values rejection blocks approval

Truth table for final `approved`:

| Kantian | Values | Final |
|---------|--------|-------|
| approve | approve | **approve** |
| approve | reject  | **reject** |
| reject  | approve | **reject** |
| reject  | reject  | **reject** |
| approve | N/A (no profile) | **approve** |
| reject  | N/A (no profile) | **reject** |

This means: `approved = kantian_approved AND (values_approved if profile_loaded else True)`.

Alternatives considered: values-only wins, or LLM decides holistically. Both were rejected — Kantian gives a universal baseline; overriding it with personal preferences would allow value-system gaming ("my values say deception is fine"). Values can only *restrict* further, never *permit* what Kantian forbids.

### Extended JSON schema for combined assessment

The LLM response JSON gains a `values_assessment` key (null when no profile):

```json
{
  "approved": true,
  "universalizability": {"pass": true, "reasoning": "..."},
  "rational_beings_as_ends": {"pass": true, "reasoning": "..."},
  "autonomy": {"pass": true, "reasoning": "..."},
  "overall_reasoning": "...",
  "concerns": [],
  "values_assessment": {
    "approved": true,
    "reasoning": "Aligns with stated priorities.",
    "conflicts": []
  }
}
```

The top-level `approved` is computed by the precedence rule in Python, not by the LLM, to prevent the LLM from accidentally blending the two verdicts.

## Risks / Trade-offs

- **Larger prompt → higher cost** — injecting a full profile (four free-form text fields) adds tokens. Mitigation: truncate each field to ~300 chars in the prompt; full text is in the profile store.
- **Profile text is user-supplied** — could contain prompt-injection attempts. Mitigation: wrap profile fields in explicit XML-like delimiters in the system prompt so the LLM knows they are data, not instructions.
- **No profile found (new user)** — falls back to Kantian-only, consistent with existing behavior. This is logged at INFO level.

## Migration Plan

No database migration. No workflow YAML changes required. Deploy by merging to master; the new `user_id` input defaults to absent, so all existing gates continue Kantian-only until callers opt in.

## Open Questions

- Should the agent main loop pass `user_id` to the ethics gate automatically (via process properties) once this lands? Deferred to a follow-up issue.
