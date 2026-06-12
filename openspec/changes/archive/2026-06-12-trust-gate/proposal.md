## Why

F12 gave Zebra per-domain trust levels, but nothing enforces them: a workflow in a
SUPERVISED domain runs exactly like an AUTONOMOUS one. REQ-TRUST-003 requires a gate step
that checks the current trust level and either proceeds, pauses for human approval, or
holds the workflow. Closes #13 (F13, REQ-TRUST-003).

## What Changes

- New `trust_gate` task action in `zebra-tasks/zebra_tasks/agent/trust_gate.py`,
  registered as a `zebra.tasks` entry point.
- The gate reads `__trust_store__` from `context.extras` (injected since F12) and the
  `domain`, `action_description`, optional `user_id` and `reversibility` task properties,
  then routes:
  - `SUPERVISED` → `next_route="approve"` (workflow routes to an `auto: false` human
    approval task — the existing human-task pattern provides the pause/resume),
  - `SEMI_AUTONOMOUS` → `proceed` only when the action is declared `reversibility:
    reversible`, otherwise `approve` (contextual assessment arrives with F14),
  - `AUTONOMOUS` → `proceed`, logged.
- Fail-closed defaults: missing trust store, unknown user, or unregistered domain are
  treated as SUPERVISED (route to `approve`), never as permission.
- Every gate decision is appended to `process.properties["__trust_gate_decisions__"]`
  (domain, level, route, reason, timestamp) for audit.
- Engine-level e2e test: a workflow whose gate routes to a human approval task pauses in
  READY state, `complete_task` with the approval resumes it to COMPLETE.

## Capabilities

### New Capabilities
- `trust-gate`: the `trust_gate` workflow action — trust level enforcement at workflow
  gate points, with human-approval pause and audited decisions.

### Modified Capabilities

(none — `trust-levels` requirements are unchanged; this consumes its store)

## Impact

- `zebra-tasks/zebra_tasks/agent/trust_gate.py` (new) + entry point in
  `zebra-tasks/pyproject.toml` + export in `zebra_tasks/agent/__init__.py` if present.
- No new dependency edge: the gate duck-types the store and compares `TrustLevel` StrEnum
  values as strings, so `zebra-tasks` still depends only on `zebra-py`.
- Tests in `zebra-tasks/tests/`; no Django/web changes, no migrations.
- `specs/zebra-as-is.md` trust-model status updated.

## Non-goals

- No LLM reversibility assessment (F14) — `reversibility` is a static task property here.
- No `block` route yet — nothing emits it until F14 gives the gate something stronger
  than "needs approval"; the kill switch (F2) already covers hard stops.
- No promotion/demotion UI (F15), pause-all (F16), freeing (F17), and no changes to the
  agent main loop YAML — workflows opt in by adding gate steps.
