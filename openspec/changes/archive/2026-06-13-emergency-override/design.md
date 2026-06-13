## Context

F12–F15 built the trust store, gates, reversibility, and the human control surface
(`/trust/` page + `/api/trust/*`). REQ-TRUST-005 needs the inverse of promotion: one
action that demotes everything to SUPERVISED. The store already has the right primitive
(`set_trust_level`, which writes an audit record); `pause_all` is a fan-out over the
domain registry. Gates read the store at execution time (F13), so "running workflows
paused at the next gate" needs no engine work — it falls out of the existing design.

## Goals / Non-Goals

**Goals:** `pause_all` store method (audited); authenticated API + web button; e2e proving
a previously-autonomous workflow requires approval after the override.

**Non-Goals:** CLI/chat surface, freeing (F17), kill-switch changes, global cross-user
halt.

## Decisions

1. **`pause_all` reuses `set_trust_level` per domain**, only touching domains that aren't
   already SUPERVISED. This keeps the "every level change writes one audit record"
   invariant — the audit requirement (REQ-TRUST-005) is satisfied by the existing change
   trail, with reason `Emergency override: <reason>`. No separate override-event table.
2. **Signature `pause_all(user_id, reason, changed_by)`.** zebra-to-be sketched
   `pause_all(user_id, reason)`, but the audit record needs the human who triggered it;
   `changed_by` is added, consistent with `set_trust_level`. Returns `list[str]` of
   reverted domains so the UI/API can report what changed.
3. **Django reverts in one `transaction.atomic()`** wrapping per-domain `_set_level_sync`
   calls (the helper already extracted in F15) — all-or-nothing, same pattern as
   `resolve_suggestion`.
4. **Per-user scope**, like the rest of the trust surface. Global hard-stop is the kill
   switch's job; this is "revoke *my* agent's autonomy".
5. **Prominent but not destructive-confirm.** The button is styled as an emergency
   control (red) and posts directly — reverting to SUPERVISED is fully reversible (the
   human can re-promote via F15), so it does not need the double-confirm that the
   irreversible freeing flow (F17) will.

## Data Model Changes

None. Reuses `zebra_trust_levels` + `zebra_trust_changes`. One new ABC method.

## API / Interface Changes

- `TrustStore.pause_all(user_id, reason, changed_by) -> list[str]`.
- `POST /api/trust/pause-all/` (body `{reason?}`) → `{reverted: [...]}`.
- Web `POST /trust/pause-all/` → redirect to `/trust/` with a message.

## Risks / Trade-offs

- [Accidental click revokes earned trust] → Fully reversible via F15 re-promotion; the
  audit trail records who/when/why, and the button label is explicit.
- [Many domains → many audit rows] → Bounded by the registry (8 domains); only
  non-SUPERVISED domains are touched.

## Spec Updates

- `openspec/specs/trust-management/spec.md` gains an ADDED emergency-override requirement
  (delta in this change).
- `specs/zebra-as-is.md` trust paragraph + F12–F17 status table (F16 implemented; F17
  pending).

## Open Questions

- None. F17's freeing flow is the next and last phase-2 item.
