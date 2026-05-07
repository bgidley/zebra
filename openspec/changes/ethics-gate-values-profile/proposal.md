## Why

The ethics gate currently applies only a universal Kantian test. It cannot account for a user's personal values (e.g. "I never want to work on gambling projects"), so goals that are Kantian-clean but personally objectionable slip through unchallenged. Closes #19.

## What Changes

- `EthicsGateAction` gains an optional `user_id` input; when present it loads the user's current `ValuesProfile` via `__profile_store__` and incorporates the profile text into the LLM prompt alongside the Kantian evaluation.
- A combined evaluation produces two verdicts: Kantian and values-based. The final `approved` flag follows a precedence rule: **Kantian rejection always overrides values approval; values approval never overrides Kantian rejection; values rejection blocks even a Kantian-approved goal; ties (both approve or both reject) follow the shared verdict**.
- The stored assessment and log include the reasoning from both evaluators, so the user can see why a goal was blocked.
- No breaking changes to existing callers — `user_id` is optional; gates without a profile store fall back to Kantian-only (existing behaviour).

## Capabilities

### New Capabilities
- `ethics-gate-values-integration`: LLM prompt and decision logic inside `EthicsGateAction` that combines a loaded values profile with the Kantian categorical imperative; Kantian precedence rule; combined assessment schema.

### Modified Capabilities
- `values-profile`: New read path — `EthicsGateAction` reads the current profile version via `ProfileStore.get_current(user_id)`; no writes, no schema changes.

## Impact

- `zebra-tasks/zebra_tasks/agent/ethics_gate.py` — primary change.
- `zebra-tasks/tests/test_ethics_gate.py` — new tests for values-combined path and precedence rule.
- No API, YAML schema, or database changes required.

## Non-goals

- Building a separate "values evaluator" action — this stays inside `EthicsGateAction`.
- Storing per-goal values assessments separately from the existing `ethics_assessment` key.
- Changing the values-profile wizard or profile store.
