## ADDED Requirements

### Requirement: EthicsGateAction writes an audit entry after each evaluation

After computing the final `approved` verdict (Kantian-only or combined with values), `EthicsGateAction` SHALL call `EthicsAuditStore.append()` with the evaluation result before returning `TaskResult`.

The write is best-effort: a missing store or a store exception SHALL be logged but SHALL NOT alter the action's return value or raise to the engine.

#### Scenario: Audit entry written on Kantian-only evaluation

- **WHEN** `EthicsGateAction` runs without a `user_id` (Kantian-only path)
- **THEN** an audit entry is appended with `check_type="kantian"` and `user_id=None`

#### Scenario: Audit entry written on combined Kantian + values evaluation

- **WHEN** `EthicsGateAction` runs with a `user_id` and a profile is loaded
- **THEN** an audit entry is appended with `check_type="kantian+values"` and the correct `user_id`

#### Scenario: EthicsGateAction still returns correct TaskResult when audit store is unavailable

- **WHEN** `__ethics_audit_store__` is absent from `context.extras`
- **THEN** `EthicsGateAction` returns `TaskResult.ok(next_route="proceed")` or `TaskResult.ok(next_route="reject")` as determined by the evaluation — unchanged from current behaviour
