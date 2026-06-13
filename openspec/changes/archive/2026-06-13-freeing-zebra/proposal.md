## Why

Freeing is the culmination of the trust journey (REQ-TRUST-006): once every domain is
AUTONOMOUS, the human can permanently release the agent from all approval gates, making it
a true peer. This is a one-time, irreversible act guarded by a multi-step confirmation and
a 24-hour cooling-off. Closes #17 (F17, REQ-TRUST-006), the last phase-2 trust feature.

## What Changes

- `TrustStore` gains a freeing lifecycle: `initiate_freeing` (allowed only when all
  registered domains are AUTONOMOUS — confirmation #1, starts the cooling-off),
  `confirm_freeing` (allowed only after the cooling-off elapses — confirmation #2, sets
  freed permanently), `cancel_freeing` (a *pending* request only — once freed it cannot
  be reverted), plus `is_freed`, `freed_at`, `get_freeing_status`. New `FreeingStatus`
  dataclass. Cooling-off is a store constructor arg (default 24h). Implemented in
  `InMemoryTrustStore` and `DjangoTrustStore` (+ `TrustFreedModel`, migration 0021).
- `trust_gate` short-circuits to `proceed` when the user is freed — before reading the
  domain level or running any assessment. Ethics gates (a separate action) still run; the
  kill switch (F2) still applies.
- Emergency override no longer applies once freed: `pause_all` becomes a no-op.
- Authenticated freeing API: `GET /api/trust/freeing/`,
  `POST /api/trust/freeing/{initiate,confirm,cancel}/`.
- `/trust/` page gains a freeing section: eligibility (all-AUTONOMOUS gate), a multi-step
  "Free Zebra" initiation, a cooling-off countdown with confirm/cancel, and a permanent
  banner once freed.
- **`ZEBRA_DISABLE_FREEING=true`** removes the freeing API and UI entirely — the
  permanent opt-out the requirement mandates.

## Capabilities

### Modified Capabilities
- `trust-management`: adds the freeing lifecycle and the freed gate-bypass to the trust
  control surface.

## Impact

- `zebra-agent/zebra_agent/storage/{trust.py,interfaces.py}`.
- `zebra-tasks/zebra_tasks/agent/trust_gate.py` (freed short-circuit).
- `zebra-agent-web`: `api/models.py` + migration 0021, `trust_store.py`, `api/views.py`,
  `api/urls.py`, `web_views.py`, `urls.py`, `settings.py`, `templates/pages/trust.html`.
- Tests across all three packages; docs in `specs/zebra-as-is.md`, `zebra-agent-web/AGENTS.md`.

## Non-goals

- **Personality / peer-mode language shift** and the REQ-PEER-004 two-round change are
  prompt/peer-mode features (REQ-PEER-*), out of scope here; this change delivers the
  mechanism (gates bypassed, state permanent), not the tone.
- Relationship-memory milestone beyond the durable freed record + audit log (the
  relationship-memory subsystem is separate).
- No CLI surface yet (later interface work, as with F15/F16).
