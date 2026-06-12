## Context

F12 landed `TrustStore` (per-(user, domain) levels, SUPERVISED default) and injected it
as `engine.extras["__trust_store__"]`. The engine already supports everything a gate
needs: conditional routing on `TaskResult.next_route`, and pausing via `auto: false`
human tasks completed through `engine.complete_task(..., next_route=...)`. F13 is the
glue: a task action that turns a trust level into a route.

## Goals / Non-Goals

**Goals:**
- `trust_gate` action: trust level → `proceed` / `approve` route, fail-closed.
- Pause/resume through the existing human-task pattern (no engine changes).
- Auditable decisions in process properties.

**Non-Goals:**
- Reversibility assessment (F14) — accepted here only as a declared task property.
- `block` route emission, trust management UI, main-loop integration.

## Decisions

1. **Gate routes; the workflow pauses.** The action never blocks the event loop waiting
   for a human. It returns `next_route="approve"`, and the workflow's routing sends the
   FOE token to an `auto: false` task, which is the engine's native pause. This reuses
   the human-task form machinery (REQ-TRUST-003's "creates a human approval task")
   without new engine states. Alternative — the gate itself becoming a waiting task —
   was rejected: it would duplicate the human-task lifecycle.
2. **No `zebra-agent` import.** `TrustLevel` is a StrEnum, so the gate compares
   `str(level)` against literal `"SUPERVISED" | "SEMI_AUTONOMOUS" | "AUTONOMOUS"`.
   Avoids deepening the known cross-package coupling leak (ethics_gate's lazy import).
3. **Fail-closed everywhere.** Missing `__trust_store__`, missing/invalid `user_id`,
   store errors, or an unrecognised level string all resolve to SUPERVISED behaviour
   (`approve`) with a logged warning. A trust gate that fails open is worse than no
   gate. This deliberately deviates from the "degrade gracefully and skip" storage rule
   — skipping enforcement is not graceful for a policy action; the deviation is logged.
4. **`SEMI_AUTONOMOUS` needs explicit `reversibility: reversible` to proceed.** Until
   F14 computes reversibility, the only safe default for undeclared actions is approval.
   The property is a static string on the task definition (`reversible` /
   `irreversible` / absent), template-resolvable so F14 can later feed it dynamically.
5. **`user_id` resolution order**: task property `user_id` (template-resolved) →
   process property `__user_id__` → fail-closed `approve` if neither yields an int.
6. **Audit lives in process properties.** Decisions append to
   `process.properties["__trust_gate_decisions__"]` (list of JSON-serialisable dicts:
   task_id, domain, user_id, level, reversibility, route, reason, decided_at ISO). The
   durable cross-process audit (TrustChangeRecord) already covers level changes; gate
   decisions are per-run context, same pattern as `__trust_assessments__` planned in
   the to-be spec. The decision is also the task output, so `{{gate_id.output}}`
   templates work.

## Data Model Changes

None. No new tables or store interface methods. New process property key:
`__trust_gate_decisions__` (appended list).

## API / Interface Changes

- New task action `trust_gate` (entry point `zebra.tasks.trust_gate`), inputs:
  `domain` (required), `action_description` (optional, template), `user_id` (optional,
  template), `reversibility` (optional: `reversible`/`irreversible`), `output_key`
  (default `trust_gate_decision`). Routes: `proceed`, `approve`.
- YAML usage matches the zebra-to-be §4 sketch (`routings` with names
  `proceed`/`approve`).
- No HTTP endpoints, no YAML schema changes.

## Risks / Trade-offs

- [Workflows can simply omit the gate] → By design in F13; gates become mandatory per
  domain manifest later (REQ-DOM work). Documented in spec.
- [Static `reversibility` property is self-declared] → Anti-gaming belongs to F14's
  contextual assessor; until then SEMI_AUTONOMOUS defaults to approval, so a missing or
  dishonest declaration can only *increase* human oversight relative to AUTONOMOUS.
- [Trust level changes mid-run] → The gate reads the store at execution time, so a
  demotion takes effect at the next gate — exactly the REQ-TRUST-005 semantics F16 needs.

## Spec Updates

- `specs/zebra-as-is.md`: trust-model weakness item and F12–F17 status table row
  (F13 implemented; F14–F17 pending).

## Open Questions

- None blocking. F14 will replace the static `reversibility` input with the contextual
  assessor and decide whether `block` becomes a real route.
