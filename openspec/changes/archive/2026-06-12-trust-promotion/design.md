## Context

F12 shipped `TrustStore` (levels + append-only change audit) with in-memory and Django
backends; F13/F14 enforce levels at gates, reading the store at execution time — so any
level change already takes effect at the next gate (REQ-TRUST-004's "immediately"
criterion). What's missing is the human control surface and the agent's sanctioned
request channel. The web app has established patterns for everything needed: sync-DRF
views with `async_to_sync` (`budget_status`), form-POST web views (`knowledge_create`),
nav items (`partials/nav_item.html`), and level badges (dashboard trust card).

## Goals / Non-Goals

**Goals:** suggestion data model + store API; `propose_trust_promotion` action; trust
API endpoints; `/trust/` page; e2e suggestion→approval flow.

**Non-Goals:** F16/F17, CLI commands, automatic promotion criteria.

## Decisions

1. **Suggestions live on `TrustStore`, not a new store.** They are trust data with the
   same lifecycle and backends; a separate ABC would add wiring for no isolation benefit.
2. **`resolve_suggestion(approve=True)` performs the level change inside the store**, in
   one transaction with the status flip (Django) — the "level only changes via
   `set_trust_level` + audit record" invariant stays inside the store rather than relying
   on every caller to make two coordinated writes. `changed_by` = resolver,
   reason = "Approved agent suggestion: <evidence excerpt>".
3. **Never-self-promote is structural, not a permission check**: the only agent-reachable
   write is `add_suggestion` (via the new action); no registered task action calls
   `set_trust_level` or `resolve_suggestion`. Web/API views require an authenticated
   session and stamp `request.user.username` as `changed_by`/`resolved_by`.
4. **Own-user scope, no staff gate** — unlike the ethics audit (staff-only), trust levels
   govern the user's own domains; any authenticated user manages their own. Multi-user
   hardening (RBAC, REQ-USR-005) is later phase work.
5. **Suggestions accept any target level.** The action is named for promotion (the
   REQ-TRUST-004 use case) but the store does not special-case direction; the human can
   set any level directly regardless.
6. **UI forms POST to thin web views** that call the store and redirect (house style for
   pages); the JSON API exists in parallel for programmatic access (explicit REQ-TRUST-004
   acceptance criterion). Same duplication pattern as `run_rate` web + API views.

## Data Model Changes

- New dataclass `TrustSuggestion` (zebra-agent).
- `TrustStore` ABC +3 methods: `add_suggestion`, `list_suggestions`,
  `resolve_suggestion`.
- New Django model `TrustSuggestionModel` (`zebra_trust_suggestions`): char36 pk,
  user_id (indexed), domain, to_level, evidence, status (pending/approved/rejected),
  created_at, resolved_at (null), resolved_by (blank). Migration 0020.

## API / Interface Changes

- Task action `propose_trust_promotion` (entry point): `domain`, `to_level`, `evidence`,
  `user_id` (→ `__user_id__` fallback), `output_key`. Output `{submitted, suggestion_id,
  status}`; graceful `submitted: False` when `__trust_store__` absent.
- HTTP API (authenticated): `GET /api/trust/`, `POST /api/trust/<domain>/`
  (`{level, reason}`), `GET /api/trust/changes/`, `GET /api/trust/suggestions/`
  (`?status=`), `POST /api/trust/suggestions/<id>/resolve/` (`{approve}`).
- Web: `GET /trust/`, `POST /trust/<domain>/set/`, `POST /trust/suggestions/<id>/resolve/`.

## Risks / Trade-offs

- [A workflow could still social-engineer the human via evidence text] → Evidence is
  displayed verbatim and clearly labelled as agent-submitted; the human decides.
- [Suggestion spam] → Out of scope; daemon/budget limits bound workflow volume, and the
  UI shows pending count. Rate limiting can come with F16 if needed.
- [Two views per mutation (web + API)] → Established house pattern; views are thin
  wrappers over the same store calls.

## Spec Updates

- New `openspec/specs/trust-management/spec.md` (on archive).
- `specs/zebra-as-is.md` trust paragraph + F12–F17 status table.

## Open Questions

- None blocking. F16's pause-all will reuse `set_trust_level` in a loop over
  `list_domains()` plus its own audit reason.
