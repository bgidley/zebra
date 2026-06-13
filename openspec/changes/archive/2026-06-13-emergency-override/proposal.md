## Why

When trust has been granted (SEMI_AUTONOMOUS / AUTONOMOUS across domains), the human needs
a single instant action to revoke all of it — the trust-layer sibling of the kill switch.
Today the only way to demote is one domain at a time via F15. REQ-TRUST-005 requires a
one-click "revert all domains to SUPERVISED" with an audit record. Closes #16 (F16,
REQ-TRUST-005).

## What Changes

- `TrustStore.pause_all(user_id, reason, changed_by)` sets every registered domain that
  is not already SUPERVISED back to SUPERVISED, writing one audit change record per
  reverted domain (reason prefixed "Emergency override:"). Returns the list of reverted
  domains. Implemented in `InMemoryTrustStore` and `DjangoTrustStore` (Django reverts in
  one transaction).
- Authenticated `POST /api/trust/pause-all/` endpoint (own-user scope) calling
  `pause_all` with `request.user.username` as `changed_by`.
- `/trust/` page gains an "Emergency Override — revert all to SUPERVISED" button
  (form-POST to a thin web view), styled as the prominent emergency control.
- Because gates read the store at execution time (F13), running autonomous workflows
  observe the revert at their next `trust_gate` — no engine change needed.

## Capabilities

### Modified Capabilities
- `trust-management`: adds the emergency-override (pause-all) requirement to the
  human trust-control surface.

## Impact

- `zebra-agent/zebra_agent/storage/{trust.py,interfaces.py}`.
- `zebra-agent-web`: `trust_store.py`, `api/views.py`, `api/urls.py`, `web_views.py`,
  `urls.py`, `templates/pages/trust.html`.
- Tests across zebra-agent, zebra-agent-web (API + e2e), zebra-tasks (gate e2e).
- Docs: `specs/zebra-as-is.md`, `zebra-agent-web/AGENTS.md`. No migration (reuses
  existing trust tables).

## Non-goals

- No CLI/chat surface yet (later interface work, as with F15); web + API only.
- No freeing flow (F17) and no change to the kill switch (F2/REQ-TRUST-007), which is a
  separate, non-trust mechanism.
- Pause-all is per-user (matching the rest of the trust surface), not a global halt — the
  kill switch already covers global hard-stop.
