## Context

REQ-TRUST-001 requires per-(user, domain) trust levels with SUPERVISED default and full
audit history. Nothing trust-related exists yet. The codebase already has a clear pattern
for this kind of layer: ABCs in `zebra-agent/zebra_agent/storage/interfaces.py`, in-memory
implementations alongside them, Django-backed implementations in
`zebra-agent-web/zebra_agent_web/*_store.py` with models in `api/models.py`, and engine
injection via `engine.extras` (see `api/agent_engine.py`, which injects
`__budget_manager__` and `__ethics_audit_store__`). F13–F17 all consume what this change
creates.

## Goals / Non-Goals

**Goals:**
- `TrustLevel` enum, `TrustChangeRecord` model, `TrustStore` ABC + two implementations.
- Domain taxonomy: canonical seeded domains, unknown domains rejected on write.
- Append-only audit trail of every trust change.
- Trust store available to workflows via `context.extras["__trust_store__"]`.
- Dashboard card showing current trust level per domain.

**Non-Goals:**
- Gate enforcement (F13), reversibility (F14), change UI/API endpoints (F15),
  pause-all (F16), freeing (F17). The dashboard is display-only.

## Decisions

1. **Models live in `zebra-agent`, not `zebra-py`** — trust is policy layered above the
   engine (zebra-to-be §4: "Trust is enforced at gates, not in actions"). `zebra-py/core`
   stays untouched. F13's `trust_gate` action reads the store from `context.extras`, so
   `zebra-tasks` needs no new dependency edge.
2. **`user_id: int`** — matches the existing `ValuesProfileStore` / `KnowledgeStore`
   convention (Django `User` pk). The to-be IdentityStore migration can widen this later.
3. **Domain taxonomy is a code-level registry** (`DOMAIN_REGISTRY` in
   `zebra_agent/storage/trust.py`) seeded with `code, scheduling, research, finance,
   health, home, creative, social`, with `register_domain()` for extension. Alternative —
   a DB table — was rejected: domains arrive as code (entry-point packages per
   REQ-PRIN-002), so a table adds migration overhead with no benefit yet.
4. **Reads never write**: `get_trust_level` returns `SUPERVISED` for unknown pairs without
   materialising a row. Avoids write-on-read surprises and keeps the audit trail to actual
   changes. `get_all_trust_levels` merges stored rows over the registry defaults.
5. **Audit is append-only by construction**: the only mutation API is `set_trust_level`,
   which writes a `TrustChangeModel` row (old level, new level, reason, changed_by,
   timestamp) in the same transaction as the level upsert. No update/delete methods.

## Data Model Changes

- New Pydantic models in `zebra-agent`: `TrustLevel` (StrEnum), `TrustChangeRecord`.
- New `TrustStore` ABC: `get_trust_level`, `set_trust_level`, `get_all_trust_levels`,
  `list_trust_changes`.
- New Django models + one migration in `zebra-agent-web/api/models.py`:
  `TrustLevelModel` (unique `(user_id, domain)`, level, updated_at) and
  `TrustChangeModel` (user_id, domain, old_level, new_level, reason, changed_by,
  created_at).

## API / Interface Changes

- `agent_engine.py` injects `engine.extras["__trust_store__"]` (DjangoTrustStore).
- Dashboard view (`web_views.py: dashboard`) gains a trust-by-domain context entry;
  `templates/pages/dashboard.html` gains a read-only trust card.
- No new HTTP endpoints, task actions, or YAML schema additions.

## Risks / Trade-offs

- [Single-user web app today: which user_id does the dashboard use?] → Use
  `request.user.pk`; store API is fully user-scoped so multi-user works later.
- [SQLite test concurrency with async store] → follow existing `sync_to_async` store
  pattern and `transaction=True` test guidance already in AGENTS.md.
- [Registry-only domains means typo'd domain in YAML fails at runtime] → `set_trust_level`
  raises `ValueError` early; F13's gate will surface unknown domains explicitly.

## Spec Updates

- `specs/zebra-as-is.md`: update gap list item 4 ("No trust model") and the F12–F17 status
  table row; reference a new `specs/trust-model-design.md` once F13+ land (this change is
  small enough to note inline).

## Open Questions

- None blocking. F13 will decide how the gate maps task `domain` properties onto the
  registry.
