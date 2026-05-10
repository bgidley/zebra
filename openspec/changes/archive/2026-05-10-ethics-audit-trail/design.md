## Context

`EthicsGateAction` writes its structured assessment into a process property (`output_key`, default `ethics_assessment`). This property is transient — it lives only as long as the process. Once a process completes or is garbage-collected, the ethics decision is gone. REQ-ETH-006 requires a durable, tamper-evident log so ethics decisions can be audited, reported, or exported.

The existing storage layer in `zebra-agent` follows a clean interface-abstraction pattern (see `storage/interfaces.py`). Django models handle Oracle persistence; in-memory implementations cover tests. The `WorkflowEngine` uses `extras` to inject stores into task actions.

## Goals / Non-Goals

**Goals:**
- Append every ethics verdict (goal text, verdict, reasoning, timestamp, process id, user id) to a durable store.
- Expose the log via a read-only REST API (`GET /api/ethics-audit/`) with filtering by date, verdict, and process id.
- Provide CSV and JSON export from the API.
- Add a UI page linked from the activity view.

**Non-Goals:**
- Modifying or deleting audit entries.
- Streaming / real-time push of audit events.
- Auditing non-ethics workflow steps.

## Decisions

### D1: New `EthicsAuditStore` interface in `storage/interfaces.py`

**Chosen**: Add `EthicsAuditStore(ABC)` alongside the existing `MemoryStore`, `MetricsStore`, `ProfileStore` pattern.

**Why**: Keeps the dependency boundary clean — `EthicsGateAction` in `zebra-tasks` takes a store from `context.extras` and calls a single `append()` method. No direct dependency on Django or Oracle.

**Alternatives**: Reuse the Django ORM directly from the task action — rejected because task actions must not import database drivers.

### D2: Django model `EthicsAuditEntry` for Oracle persistence

**Chosen**: A new Django model with `db_table = "ethics_audit_entry"`. No `update`/`delete` on the ORM class (enforced by overriding `save()`/`delete()` to raise `NotImplementedError`).

**Why**: Oracle is already the production DB for the agent; Django migrations provide schema management. Immutability is enforced at the model layer, not just by convention.

**Alternatives**: A flat append-only text log — rejected because it cannot be queried or filtered.

### D3: Async `OracleEthicsAuditStore` wraps ORM with `sync_to_async`

**Chosen**: Follow the same pattern as existing Oracle stores (e.g., `ProfileStore`). The `append()` method wraps the Django ORM call in `sync_to_async`.

**Why**: Consistent with the rest of the codebase; avoids blocking the asyncio event loop.

### D4: Read-only DRF endpoint — function-based views, not a ViewSet

**Chosen**: `@api_view(["GET"])` functions at `/api/ethics-audit/` (list + filter) and `/api/ethics-audit/<id>/` (detail). Export via `?format=csv` query param.

**Why**: The existing `views.py` uses function-based views; no ModelSerializer/Router pattern established. Keeping it simple avoids introducing a new pattern for a read-only endpoint.

### D5: Extras key `__ethics_audit_store__`

The store is injected via `context.extras["__ethics_audit_store__"]`. Absence is tolerated: `EthicsGateAction` logs a warning and skips the write (same pattern as `__profile_store__`).

## Risks / Trade-offs

- **High audit write volume**: Each ethics evaluation does a DB write in the hot path. Mitigation: the write is async and non-blocking; if it fails, log the error and continue (do not fail the evaluation).
- **SQLite in tests**: SQLite is used for unit tests. The in-memory store avoids SQLite entirely for unit tests; Oracle E2E covers the real path.
- **Schema migration**: Adding `ethics_audit_entry` table requires a migration. Must run `makemigrations` + `ruff format` (per project convention) before committing.

## Migration Plan

1. Add `EthicsAuditEntry` Django model + generate migration.
2. Add `EthicsAuditStore` interface + `InMemoryEthicsAuditStore` + `OracleEthicsAuditStore`.
3. Wire store into `IoCContainer` / `WorkflowEngine` extras.
4. Update `EthicsGateAction` to write audit entry (optional, degrades gracefully).
5. Add REST API endpoint + serializer.
6. Add UI page.
7. Add unit + e2e tests.

Rollback: the audit write is optional — disabling the `__ethics_audit_store__` extras key reverts to old behaviour without code changes.

## Open Questions

- Should the audit log be visible to all users or only admins? (Assumed: admin/staff only for now, matching the activity view.)
- Export scope: all-time or paginated? (Assumed: paginated list with optional date-range filter for export.)
