## Why

Every ethics evaluation produces a structured assessment but it is written only into transient process properties — once the process ends the verdict is gone. REQ-ETH-006 requires an immutable, queryable audit log so decisions can be reviewed, exported, and used to demonstrate compliance. Closes #20.

## What Changes

- New `EthicsAuditStore` interface and Oracle/in-memory implementations persist every evaluation result.
- `EthicsGateAction` writes an audit entry (process id, goal, verdict, reasoning, timestamp) after each evaluation.
- New Django REST endpoint and UI page to list, filter, and export audit entries.
- `WorkflowEngine` extras key `__ethics_audit_store__` wires the store into the action.

## Capabilities

### New Capabilities

- `ethics-audit-trail`: Immutable append-only log of every ethics evaluation; queryable by date range, verdict, or process id; exportable as CSV/JSON.

### Modified Capabilities

- `ethics-gate-values-integration`: `EthicsGateAction` gains a side-effect — writing to the audit store — but the existing evaluation logic and stored assessment schema are unchanged.

## Impact

- `zebra-tasks/zebra_tasks/agent/ethics_gate.py` — add optional audit write call.
- New `zebra-agent/zebra_agent/stores/ethics_audit_store.py` with interface + Oracle + in-memory impls.
- New Django model `EthicsAuditEntry` (append-only, no update/delete).
- New DRF viewset + URL at `/api/ethics-audit/`.
- New migration for `EthicsAuditEntry` table.
- `zebra-agent-web` UI: new page linked from the activity view.

## Non-goals

- Modifying past audit entries (immutability is a hard requirement).
- Real-time streaming of audit events.
- Audit log for non-ethics workflow steps.
