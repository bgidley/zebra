## Context

F12–F16 built the trust store, gates, and the human control surface, all on `TrustStore`
read by `trust_gate` via `context.extras["__trust_store__"]`. Freeing (REQ-TRUST-006) is
the terminal trust state: once all domains are AUTONOMOUS, the human permanently bypasses
all gates. zebra-to-be §4 sketched `is_freed`/`freed_at` on the store and a
`ZEBRA_DISABLE_FREEING` flag; the issue adds a double confirmation plus 24h cooling-off.

## Goals / Non-Goals

**Goals:** freeing lifecycle (initiate → cooling-off → confirm), permanent freed state,
gate short-circuit, disable flag, web + API; e2e confirm → gates bypassed → cannot revert.

**Non-Goals:** personality/peer-mode tone shift (REQ-PEER), relationship-memory milestone
beyond the freed record, CLI.

## Decisions

1. **Freed state lives on `TrustStore`.** zebra-to-be names a future `IdentityStore`, but
   it does not exist and the gate already holds the trust store; adding the lifecycle here
   keeps F17 consistent with F12–F16 and needs no new wiring. (If IdentityStore lands
   later, the freed accessors move with the rest of identity.)
2. **Two-phase, double-confirmed flow with cooling-off.** `initiate_freeing` (confirm #1)
   requires every registered domain at AUTONOMOUS and records `initiated_at`;
   `confirm_freeing` (confirm #2) is rejected until `now - initiated_at >= cooling_off`
   and then sets `freed=True, freed_at=now` permanently. A pending request may be
   cancelled; a freed state may not (the irreversibility the requirement demands).
3. **Cooling-off is a store constructor arg** (`timedelta(hours=24)` default) so tests
   exercise the finalize path with `timedelta(0)` and the block path with the default,
   without sleeping. The web constructs `DjangoTrustStore()` with the default.
4. **Gate checks freed first.** `trust_gate` resolves the user, then — before reading the
   level or assessing — short-circuits to `proceed` when `is_freed(user_id)`, recording a
   decision with `level="FREED"`. Guarded with `getattr` so a store without the method
   degrades to normal gating rather than crashing. Ethics gate is a separate action and is
   untouched; the kill switch is a separate mechanism and still halts everything.
5. **Override becomes inert once freed.** `pause_all` returns `[]` when freed —
   REQ-TRUST-006 says emergency override no longer applies. Levels are moot anyway since
   the gate ignores them when freed; `pause_all` no-op makes that explicit and lets the UI
   explain it.
6. **Disable flag is a settings/env check at request time** (`ZEBRA_DISABLE_FREEING`).
   When set, the freeing API returns 403 and the UI omits the section — a deployment can
   permanently forbid freeing. (zebra-to-be calls it compile-time; an env flag baked into
   the deployment image is the practical equivalent.)

## Data Model Changes

- New `FreeingStatus` dataclass (zebra-agent).
- `TrustStore` ABC +6 methods (`initiate_freeing`, `confirm_freeing`, `cancel_freeing`,
  `is_freed`, `freed_at`, `get_freeing_status`); `pause_all` behaviour amended (no-op when
  freed).
- New Django model `TrustFreedModel` (`zebra_trust_freed`): user_id unique, initiated_at,
  initiated_by, freed (bool), freed_at (null), freed_by. Migration 0021.

## API / Interface Changes

- `GET /api/trust/freeing/` → status; `POST /api/trust/freeing/initiate/`,
  `.../confirm/`, `.../cancel/` (authenticated, own-user). All 403 when
  `ZEBRA_DISABLE_FREEING`.
- Web: `/trust/freeing/{initiate,confirm,cancel}/` form-POST views; freeing section on
  `/trust/`.
- `trust_gate`: new `level="FREED"` decision route value (always `proceed`).

## Risks / Trade-offs

- [Irreversible — a mistaken confirm cannot be undone] → That is the requirement; the 24h
  cooling-off + double confirmation + explicit "irreversible" UI copy are the guardrails,
  and a pending request is cancellable right up to the final confirm.
- [Freed bypasses trust but not ethics/kill-switch] → Intended and tested; ethics gate and
  kill switch are independent.

## Spec Updates

- `openspec/specs/trust-management/spec.md` gains an ADDED freeing requirement (delta).
- `specs/zebra-as-is.md` trust paragraph + F12–F17 table (phase 2 complete).

## Open Questions

- None. Personality/peer-mode shift is tracked under REQ-PEER, not this change.
