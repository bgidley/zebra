## Why

Trust levels (F12) can only be changed through the store API in tests — there is no
human-facing control, and the agent has no sanctioned way to request more autonomy.
REQ-TRUST-004 requires human-only promotion/demotion with an API endpoint and UI,
agent-submitted promotion *suggestions* (never self-promotion), and viewable change
history. Closes #15 (F15, REQ-TRUST-004).

## What Changes

- `TrustStore` gains a suggestion API: `add_suggestion` (always created `pending`),
  `list_suggestions`, `resolve_suggestion` (approve atomically performs
  `set_trust_level` with the resolver as `changed_by`; reject only flips status).
  New `TrustSuggestion` dataclass; implemented in `InMemoryTrustStore` and
  `DjangoTrustStore` (+ `TrustSuggestionModel`, migration 0020).
- New `propose_trust_promotion` task action (zebra-tasks entry point): the agent's only
  trust-related write path — it creates pending suggestions and has no code path to
  `set_trust_level`. That is the never-self-promote enforcement: no registered action
  mutates levels.
- Authenticated JSON API (own-user scope): `GET /api/trust/`, `POST /api/trust/<domain>/`
  (set level with reason — promotion and demotion), `GET /api/trust/changes/`,
  `GET /api/trust/suggestions/`, `POST /api/trust/suggestions/<id>/resolve/`.
- Web UI: `/trust/` page — per-domain level controls, pending suggestions with
  Approve/Reject, change history table; nav item; dashboard trust card links to it.
- E2E (issue #15 criterion): agent action submits a suggestion → appears pending via the
  API → user approves → level changes with the human recorded as `changed_by`.

## Capabilities

### New Capabilities
- `trust-management`: human-only trust level changes (API + UI), agent promotion
  suggestions, and change-history visibility.

### Modified Capabilities

(none — `trust-levels` and `trust-gate` requirements are unchanged; the suggestion API
is additive)

## Impact

- `zebra-agent/zebra_agent/storage/{trust.py,interfaces.py,__init__.py}`.
- `zebra-agent-web`: `api/models.py` + migration, `trust_store.py`, `api/views.py`,
  `api/urls.py`, `web_views.py`, `urls.py`, `templates/pages/trust.html`,
  `templates/base.html`, dashboard template.
- `zebra-tasks`: new action + entry point.
- Docs: `specs/zebra-as-is.md`, `zebra-tasks/AGENTS.md`, `zebra-agent-web/AGENTS.md`.

## Non-goals

- No pause-all (F16) or freeing flow (F17); no CLI trust commands (later interface work).
- No automatic promotion criteria — suggestions carry free-text evidence; judgment stays
  with the human.
- Agent main loop unchanged; workflows opt into proposing via the new action.
