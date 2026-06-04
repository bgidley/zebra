---
name: f28-event-bus
description: Forward spec for event-driven trigger bus — in-process asyncio pub/sub, EventLog, webhook intake, TriggerRegistry
metadata:
  type: feature-spec
  issue: "#28"
  requirement: REQ-PRIN-009
  status: NOT IMPLEMENTED — forward spec
---

# F28: Event-Driven Trigger Bus

**GitLab issue**: #28  
**Requirement**: REQ-PRIN-009  
**Status**: NOT IMPLEMENTED — this is a forward spec. The issue was closed as deferred, not as done. No `EventBus`, `TriggerRegistry`, `EventLog`, or webhook endpoint exists in the codebase.

## Goal & scope

In-process asyncio pub/sub bus + external event intake (webhook endpoint). Triggers subscribe to events → start workflows. Phase 2 Redis backend is explicitly out of scope.

See `zebra-to-be.md` §7 for the full target design.

## Data model changes

**`EventRecord`** (new Django model `zebra_event_records`):
```
id, event_type, source, payload (JSON), timestamp, user_id,
idempotency_key, state (pending|processing|processed|dead_lettered)
```

**`TriggerDefinition`** (new Django model `zebra_trigger_definitions`):
```
id, name, event_type_pattern, filter_expression (JSON), workflow_name,
cooldown_seconds, user_id, enabled
```

## API / interface changes

**New module**: `zebra-agent/zebra_agent/events/`
- `EventBus` ABC: `publish(event)`, `subscribe(pattern, handler)`, `recover()`
- `InProcessEventBus`: asyncio queue + `EventLog`
- `TriggerRegistry`: entry-point discovery (`zebra.triggers`), `fire(event) -> list[Action]`
- `NullEventBus`: no-op for when bus is disabled

**New REST endpoints**:
- `POST /events/intake/<integration>/` — webhook intake with per-integration signature verification
- `GET /events/` — event log browser
- `GET /events/<id>/` — event detail
- `GET /triggers/`, `POST /triggers/`, `DELETE /triggers/<id>/` — trigger CRUD

**New entry-point group**: `zebra.triggers` (mirrors `zebra.tasks` pattern)

**Injection**: `extras["__event_bus__"]` — `NullEventBus` when `EVENT_BUS_ENABLED=false`

## Control flow

```
webhook POST
  → signature verify (per-integration)
  → normalise to EventRecord
  → EventLog.append (persisted)
  → asyncio.Queue.put
  → fan-out coroutine:
       TriggerRegistry.fire(event)
         → cooldown check
         → trust gate (process trust level for trigger domain)
         → engine.create_process() → engine.start_process()
         → mark EventRecord processed
       on failure → DeadLetterStore
  
Startup: EventBus.recover() replays pending/processing records
```

## Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `EVENT_BUS_ENABLED` | `false` | Enable the bus |
| `EVENT_LOG_RETENTION_DAYS` | 30 | How long to keep processed events |
| `EVENT_DEAD_LETTER_RETENTION_DAYS` | 90 | Dead-letter retention |
| `WEBHOOK_SIGNING_SECRET` | — | Default HMAC secret (per-integration overrides in `CredentialStore`) |

## Open questions / risks

1. **TrustStore not yet implemented** (F12-F17 pending) — trust gate in trigger path needs the full trust data model.
2. **Per-integration signing verifiers** not designed — each integration needs its own verification scheme (HMAC, RSA, etc.).
3. **In-process queue doesn't survive mid-fan-out restart** — mitigated by `EventLog.recover()` on startup, but handlers must be idempotent.
4. **`TriggerStore` interface** not yet defined — how user-defined triggers are stored and versioned.
5. **Webhook endpoint auth** — intake endpoint must be publicly reachable but needs anti-replay protection.
