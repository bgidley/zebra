## Why

The trust & autonomy layer (REQ-TRUST-001..006) has no foundation: there is no notion of
per-domain trust anywhere in the codebase. Every later phase-2 feature — `trust_gate` (F13),
reversibility assessment (F14), promotion/demotion (F15), emergency override (F16), freeing
(F17) — needs a persistent, auditable trust-level store and a domain taxonomy to hang off.
Closes #12 (F12, REQ-TRUST-001).

## What Changes

- New `TrustLevel` enum (`SUPERVISED` / `SEMI_AUTONOMOUS` / `AUTONOMOUS`) and
  `TrustChangeRecord` model in `zebra-agent`.
- New `TrustStore` ABC: `get_trust_level(user_id, domain)`, `set_trust_level(user_id,
  domain, level, reason, changed_by)`, `get_all_trust_levels(user_id)`,
  `list_trust_changes(user_id, domain=None)`. Unknown (user, domain) pairs read as
  `SUPERVISED`; every change appends an immutable audit record.
- Domain taxonomy registry: a canonical list of domains (`code`, `scheduling`, `research`,
  `finance`, `health`, `home`, `creative`, `social`) seeded in code, extensible without
  engine changes; `set_trust_level` rejects unknown domains.
- `InMemoryTrustStore` (zebra-agent) and `DjangoTrustStore` + `TrustLevelModel` /
  `TrustChangeModel` (zebra-agent-web, Oracle-backed, migration included).
- Trust store injected via `ExecutionContext.extras["__trust_store__"]` so workflows and
  future gate actions can query it.
- Dashboard panel showing each domain's current trust level for the active user.

## Capabilities

### New Capabilities
- `trust-levels`: per-(user, domain) trust level storage with SUPERVISED default, domain
  taxonomy registry, append-only trust change audit trail, and dashboard visibility.

### Modified Capabilities

(none — no existing spec's requirements change)

## Impact

- `zebra-agent/zebra_agent/storage/interfaces.py` (+ new `trust.py`): ABC, enum, models,
  in-memory implementation, domain registry.
- `zebra-agent-web/zebra_agent_web/api/models.py` + migration: two new tables.
- `zebra-agent-web/zebra_agent_web/trust_store.py`: Django-backed store.
- Engine wiring (`engine.py` extras) and dashboard view/template.
- No changes to `zebra-py/zebra/core/` — trust is layered above the engine.

## Non-goals

- No `trust_gate` action or enforcement (F13), no reversibility assessment (F14).
- No promotion/demotion UI or agent promotion requests (F15) — the dashboard is read-only;
  `set_trust_level` is exercised via store API and tests only.
- No pause-all / freeing flows (F16/F17).
