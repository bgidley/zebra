## 1. Branch Setup

- [x] 1.1 Create branch `f20/ethics-audit-trail` from `master`

## 2. Data Model — `EthicsAuditStore` Interface

- [x] 2.1 Add `EthicsAuditEntry` dataclass (or Pydantic model) to `zebra-agent/zebra_agent/storage/interfaces.py` with fields: `id`, `process_id`, `goal`, `approved`, `overall_reasoning`, `check_type`, `user_id`, `evaluated_at`
- [x] 2.2 Add `EthicsAuditStore(ABC)` interface to `storage/interfaces.py` with `append(entry)`, `list(approved, process_id, from_date, to_date, limit, offset)`, and `get(id)` abstract methods
- [x] 2.3 Implement `InMemoryEthicsAuditStore` in `zebra-agent/zebra_agent/storage/ethics_audit.py`
- [x] 2.4 Write unit tests for `InMemoryEthicsAuditStore` covering append, list filtering, and immutability enforcement

## 3. Django Model & Migration

- [x] 3.1 Add `EthicsAuditEntry` Django model in `zebra-agent-web/zebra_agent_web/models.py` (or a new `ethics_audit.py`) with `db_table = "ethics_audit_entry"`, override `save()`/`delete()` to raise `NotImplementedError` on existing rows
- [x] 3.2 Run `uv run python manage.py makemigrations` and verify migration file
- [x] 3.3 Run `uv run ruff check --fix . && uv run ruff format .` to fix any E501/style issues in the generated migration
- [x] 3.4 Implement `OracleEthicsAuditStore` in `zebra-agent-web/zebra_agent_web/storage/ethics_audit.py` wrapping the Django ORM with `sync_to_async`
- [x] 3.5 Wire `OracleEthicsAuditStore` into the IoC container / `WorkflowEngine` extras under key `__ethics_audit_store__`

## 4. EthicsGateAction Integration

- [x] 4.1 Update `EthicsGateAction.run()` in `zebra-tasks/zebra_tasks/agent/ethics_gate.py` to call `audit_store.append()` after computing the final verdict (best-effort: catch exceptions, log error, continue)
- [x] 4.2 Write unit tests for the audit write path: store present + success, store absent (warning logged), store raises (error logged, TaskResult unchanged)

## 5. REST API

- [x] 5.1 Add `EthicsAuditEntrySerializer` in `zebra-agent-web/zebra_agent_web/api/serializers.py`
- [x] 5.2 Add `GET /api/ethics-audit/` view function in `views.py` with filtering by `approved`, `process_id`, `from_date`, `to_date`; restrict to `IsAdminUser`
- [x] 5.3 Add `GET /api/ethics-audit/<id>/` detail view
- [x] 5.4 Add CSV export via `?format=csv` query param (returns `text/csv` with `Content-Disposition` header)
- [x] 5.5 Register URLs in `zebra-agent-web/zebra_agent_web/api/urls.py`
- [x] 5.6 Write API tests: list (unfiltered), filter by verdict, filter by date range, unauthenticated → 403, non-staff → 403, DELETE → 405, CSV export

## 6. Web UI

- [x] 6.1 Add Django template `zebra-agent-web/zebra_agent_web/templates/ethics_audit.html` rendering a table of audit entries (date, goal truncated, verdict badge, check type, process id)
- [x] 6.2 Add Django view + URL at `/ethics-audit/` (staff-only, login required)
- [x] 6.3 Add link to ethics audit page in the activity view template / main nav

## 7. Documentation

- [x] 7.1 Update `specs/zebra-as-is.md` to reference the new ethics audit trail capability
- [ ] 7.2 Run `uv run ruff check --fix . && uv run ruff format .` across all changed packages

## 8. Final Verification

- [x] 8.1 Run `uv run pytest zebra-tasks/tests/ zebra-agent/tests/ zebra-agent-web/tests/ -v --ignore=zebra-agent-web/tests/e2e_live` and confirm all pass
- [x] 8.2 Push to GitLab and verify CI pipeline (lint → unit → e2e) is green
- [x] 8.3 Open GitHub PR referencing GitLab issue #20
