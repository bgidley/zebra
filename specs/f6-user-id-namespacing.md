---
name: f6-user-id-namespacing
description: user_id columns added to all Django store tables; CurrentUserMiddleware propagates authenticated user via ContextVar
metadata:
  type: feature-spec
  issue: "#6"
  requirement: REQ-USR-002
  status: implemented
---

# F6: user_id Namespacing Across Stores

**GitLab issue**: #6  
**Requirement**: REQ-USR-002  
**Status**: Implemented

## Goal & scope

Add `user_id` to every store's read/write path so data is scoped per user. Single-tenant deployments use the single authenticated user's Django PK; the API is user-ready for multi-tenant work.

Out of scope: abstract interface changes (store ABCs still have no `user_id` parameter — scoping is entirely in the Django implementations).

## Data model changes

Migration `0011_user_id_columns` — added nullable `user_id = IntegerField(null=True, blank=True, db_index=True)` to six models:

| Model | Table |
|-------|-------|
| `ProcessInstanceModel` | `zebra_process_instances` |
| `TaskInstanceModel` | `zebra_task_instances` |
| `WorkflowRunModel` | `zebra_workflow_runs` |
| `TaskExecutionModel` | `zebra_task_executions` |
| `WorkflowMemoryModel` | `zebra_workflow_memory` |
| `ConceptualMemoryModel` | `zebra_conceptual_memory` |

Existing rows were backfilled using: process properties for runs, parent-record inheritance for tasks/FOEs, and first-user fallback for memory entries.

`user_id` values are Django `auth.User.pk` integers. No FK constraint — referential integrity is intentionally relaxed to allow user deletion without cascade.

## Implementation

**`CurrentUserMiddleware`** (`zebra_agent_web/middleware.py`):
- Sets a Python `contextvars.ContextVar` at the start of each HTTP request with the authenticated user's PK.
- `get_current_user_id()` helper reads it from anywhere in the call stack.
- Returns `None` in daemon/background context where no user is associated with the thread.

**Django store implementations** (all in `zebra_agent_web/`):
- `DjangoMemoryStore` — `get_episodic_memories`, `get_conceptual_memories` etc. all call `.filter(user_id=uid)` when `uid` is not None.
- `DjangoMetricsStore` — similar filter on `WorkflowRunModel` and `TaskExecutionModel`.
- `DjangoStore` (state store) — `user_id` stamped on `ProcessInstanceModel` at creation.
- Daemon writes (no HTTP context) produce `user_id=None` rows; these are visible system-wide but invisible to per-user list queries.

**Abstract interfaces unchanged** — `MemoryStore` and `MetricsStore` ABCs in `zebra_agent/storage/interfaces.py` have no `user_id` parameter. The single-tenant assumption lives in the Django layer.

## Configuration

None. The `user_id` is resolved from `request.user.pk` via `CurrentUserMiddleware`. No env var needed.

## Open questions / risks

- **`clear_conceptual_memories` wipes all users** — a latent multi-user bug; method ignores `user_id` filter. Must be fixed before multi-user rollout.
- **No FK constraint** — deleting a Django User leaves orphaned rows; a future `data delete --user` command must clean these up explicitly.
- **Daemon rows** with `user_id=None` are invisible to per-user reads but accumulate. Budget totals intentionally ignore user scope.
- **Abstract interfaces not updated** — adding `user_id` to the ABCs is deferred; the to-be design calls for this in a future migration. Until then, `InMemoryMemoryStore` etc. are not user-scoped at all.
