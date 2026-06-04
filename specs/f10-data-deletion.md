# F10: Data Deletion (REQ-DATA-005)

**GitLab issue**: #10
**Status**: Implemented

## Goal & scope

Provide a "delete my data" flow that removes all user-scoped records, locally and immediately. Two modes:

- **Soft delete** (default): marks knowledge entries with `deleted_at`; retained for potential audit. No rows physically removed.
- **Hard delete**: permanently removes every row scoped to `user_id` from all tables. Irreversible.

Ethics audit entries are intentionally excluded from hard delete — they are append-only and serve as an audit trail even under user request (the spec notes user-requested deletion is explicitly allowed but audit log retention is a separate policy decision for later).

Out of scope: cloud sync purge, encryption key wipe, blob filesystem cleanup.

## Data model changes

No new migrations required. The deletion service operates on existing columns:

- `KnowledgeEntryModel.deleted_at` (already exists) — set to now() on soft delete
- All other models are hard-deleted by `user_id` FK filter

## API / interface changes

### REST endpoint

`DELETE /api/user-data/` — deletes the current authenticated user's data.

Query params:
- `hard=true` — physical deletion (default: soft)

Request body (required for hard delete only):
```json
{"confirm": "delete my data"}
```

Response (200):
```json
{
  "user_id": 1,
  "hard": true,
  "totals": {
    "processes": 3,
    "tasks": 7,
    "flows_of_execution": 3,
    "process_locks": 0,
    "workflow_runs": 2,
    "task_executions": 0,
    "workflow_memories": 2,
    "conceptual_memories": 1,
    "knowledge_entries": 5,
    "profile_versions": 1,
    "profiles": 1,
    "grand_total": 25
  },
  "errors": []
}
```

### Management command

```bash
python manage.py delete_data --user <id_or_username> [--hard] [--yes]
```

- `--user` — integer user ID or username (required)
- `--hard` — physical delete (default: soft)
- `--yes` — skip confirmation prompt

### Service class

`zebra_agent.deletion.DataDeletor` — async service, works via `asgiref.sync_to_async` for ORM access.

```python
from zebra_agent.deletion import DataDeletor

report = await DataDeletor().delete_user_data(user_id=1, hard=True)
print(report.total())  # grand total of affected rows
```

## Control flow

Hard delete order (single atomic transaction):

1. Collect `process_ids` for user
2. Delete `TaskInstanceModel` where `process_id__in`
3. Delete `FlowOfExecutionModel` where `process_id__in`
4. Delete `ProcessLockModel` where `process_id__in`
5. Delete `ProcessInstanceModel` where `user_id`
6. Delete `WorkflowRunModel` where `user_id` (cascades `TaskExecutionModel`)
7. Delete `WorkflowMemoryModel` where `user_id`
8. Delete `ConceptualMemoryModel` where `user_id`
9. Delete `KnowledgeEntryModel` where `user_id`
10. Collect `profile_ids`, delete `ValuesProfileVersionModel`, then `ValuesProfileModel`

Soft delete: single UPDATE on `KnowledgeEntryModel` setting `deleted_at = now()` where `deleted_at IS NULL`.

## Configuration

None — no new settings or env vars.

## Open questions / risks

- Ethics audit entries are excluded from hard delete. If the policy changes, `EthicsAuditEntryModel` has a `user_id` column and deletion support can be added to `_hard_delete_sync`.
- `TaskExecutionModel` CASCADE-deletes when `WorkflowRunModel` is removed. The count in `DeletionReport` does not separately track task executions removed via CASCADE.
- Blob filesystem cleanup (`~/.zebra/blobs/<user_id>/`) is out of scope for this implementation.
