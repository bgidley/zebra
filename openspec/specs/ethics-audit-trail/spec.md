# ethics-audit-trail Specification

## Purpose
TBD - created by archiving change ethics-audit-trail. Update Purpose after archive.
## Requirements
### Requirement: Ethics evaluation results are appended to an immutable audit log

After every execution of `EthicsGateAction`, the system SHALL append an audit entry to the `EthicsAuditStore` containing: `process_id`, `goal` (first 500 chars), `approved` (bool), `overall_reasoning`, `check_type` (`kantian` or `kantian+values`), `user_id` (nullable), and `evaluated_at` (UTC timestamp).

The audit store is injected via `context.extras["__ethics_audit_store__"]`. When the store is absent the action SHALL log a warning and continue without writing — the ethics evaluation itself is unaffected.

#### Scenario: Audit entry written after approved evaluation

- **WHEN** `EthicsGateAction` runs and the LLM returns `approved: true`
- **THEN** an audit entry is appended with `approved=True`, the goal text, and the overall reasoning

#### Scenario: Audit entry written after rejected evaluation

- **WHEN** `EthicsGateAction` runs and the LLM returns `approved: false`
- **THEN** an audit entry is appended with `approved=False` and the rejection reasoning

#### Scenario: Missing audit store is tolerated gracefully

- **WHEN** `__ethics_audit_store__` is not in `context.extras`
- **THEN** `EthicsGateAction` logs a WARNING and completes normally without writing an audit entry

#### Scenario: Audit write failure does not fail the evaluation

- **WHEN** the audit store raises an exception during `append()`
- **THEN** `EthicsGateAction` logs an ERROR and returns its normal `TaskResult` (approved or rejected)

### Requirement: Audit entries are queryable via REST API

The system SHALL expose a read-only REST endpoint `GET /api/ethics-audit/` that returns a paginated list of audit entries, newest first. The endpoint SHALL accept optional query parameters: `approved` (bool), `process_id` (string), `from_date` (ISO-8601 date), `to_date` (ISO-8601 date).

Access SHALL be restricted to authenticated staff/admin users.

#### Scenario: List all audit entries

- **WHEN** an authenticated admin issues `GET /api/ethics-audit/`
- **THEN** the response is a paginated JSON array of audit entries ordered by `evaluated_at` descending

#### Scenario: Filter by verdict

- **WHEN** the request includes `?approved=false`
- **THEN** only rejected evaluations are returned

#### Scenario: Filter by date range

- **WHEN** the request includes `?from_date=2026-01-01&to_date=2026-01-31`
- **THEN** only entries with `evaluated_at` within that range (inclusive) are returned

#### Scenario: Unauthenticated request is rejected

- **WHEN** an unauthenticated client requests `GET /api/ethics-audit/`
- **THEN** the response is `401 Unauthorized`

#### Scenario: Non-staff request is rejected

- **WHEN** a logged-in non-staff user requests `GET /api/ethics-audit/`
- **THEN** the response is `403 Forbidden`

### Requirement: Audit log is exportable as CSV and JSON

The `GET /api/ethics-audit/` endpoint SHALL support an `Accept` header or `?format=csv` query parameter. When `format=csv` is requested the response SHALL be a `text/csv` file with all matching entries (up to a configurable max, default 10 000).

#### Scenario: Export as CSV

- **WHEN** an admin requests `GET /api/ethics-audit/?format=csv`
- **THEN** the response has `Content-Type: text/csv` and `Content-Disposition: attachment; filename="ethics-audit.csv"` with one row per entry

#### Scenario: Export as JSON (default)

- **WHEN** an admin requests `GET /api/ethics-audit/` with no format parameter
- **THEN** the response has `Content-Type: application/json`

### Requirement: Audit entries are visible in the web UI

The system SHALL provide a UI page at `/ethics-audit/` listing recent ethics audit entries in a table with columns: date/time, goal (truncated), verdict, check type, process id. A link to this page SHALL appear in the main navigation or activity view.

#### Scenario: UI page renders audit table

- **WHEN** an admin navigates to `/ethics-audit/`
- **THEN** the page displays a table of audit entries, newest first

#### Scenario: UI page linked from activity view

- **WHEN** an admin views the activity page
- **THEN** a link to the ethics audit log is visible

### Requirement: Audit entries are immutable

The system SHALL NOT expose update or delete operations on audit entries at any layer (API, ORM, or store interface). Any attempt to update or delete an audit entry SHALL raise an error.

#### Scenario: DELETE request is rejected

- **WHEN** any client issues `DELETE /api/ethics-audit/<id>/`
- **THEN** the response is `405 Method Not Allowed`

#### Scenario: ORM save on existing entry raises error

- **WHEN** code calls `.save()` on an existing `EthicsAuditEntry` Django model instance
- **THEN** a `NotImplementedError` is raised

