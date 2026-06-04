# F9: Data Export (REQ-DATA-003)

GitLab issue: #9

## Goal & scope

Users can export all their personal data as a single portable ZIP archive for
backup, migration, or audit. The ZIP is self-contained and human-readable.

**Out of scope:** encryption, incremental exports, resumable uploads, cloud sync.

## Archive format (format_version: 1)

```
zebra-export-<YYYY-MM-DD>.zip
├── manifest.json      — envelope metadata
├── processes.json     — workflow process instances + tasks
├── memory.json        — episodic (workflow) + conceptual memory entries
├── metrics.json       — workflow run records
├── knowledge.json     — personal knowledge entries
└── workflows/
    └── <name>.yaml    — user workflow YAML files
```

### manifest.json

```json
{
  "format_version": 1,
  "user_id": "42",
  "exported_at": "2025-06-04T10:00:00+00:00",
  "sections": ["processes", "memory", "metrics", "knowledge", "workflows"]
}
```

`sections` lists only the sections actually written. If a store was unavailable
(e.g., in a standalone CLI context), its section still appears in the JSON file
but with an empty list and a `"note"` field explaining the omission.

### processes.json

```json
{
  "processes": [
    {
      "id": "...",
      "definition_id": "...",
      "state": "complete",
      "properties": {...},
      "tasks": [...]
    }
  ]
}
```

### memory.json

```json
{
  "workflow_memories": [ <WorkflowMemoryEntry.to_dict()> ],
  "conceptual_memories": [ <ConceptualMemoryEntry.to_dict()> ]
}
```

### metrics.json

```json
{
  "runs": [
    {
      "id": "...", "workflow_name": "...", "goal": "...",
      "started_at": "...", "completed_at": "...",
      "success": true, "cost": 0.05, "tokens_used": 1200
    }
  ]
}
```

### knowledge.json

```json
{
  "entries": [
    {
      "id": "...", "category": "preferences", "key": "theme",
      "value": "dark", "source": "human", "confidence": 1.0,
      "deleted_at": null
    }
  ]
}
```

Soft-deleted entries are included (`include_deleted=True`) so the export is
complete for audit purposes.

## Data model changes

No new database tables or migrations. The exporter reads from existing stores
via their abstract interfaces.

## API / interface changes

| Surface | Change |
|---------|--------|
| `zebra_agent.export.DataExporter` | New service class |
| `GET /api/export/` | New endpoint — returns ZIP download (auth required) |
| `python manage.py export_data --user <id> --out <file>` | New management command |
| `agent_engine.get_knowledge()` | New accessor added to `agent_engine.py` |

## Control flow

1. Client sends `GET /api/export/` (authenticated).
2. `export_data` view resolves `user_id` from `request.user`.
3. `_export_data_impl()` runs `DataExporter.export_user_data()` via `async_to_sync`.
4. `DataExporter` queries each store in turn, serialises results to JSON, and
   packs them into an in-memory ZIP buffer.
5. View returns the buffer as `application/zip` with a
   `Content-Disposition: attachment` header.

Errors in individual store queries are caught and logged; the section still
appears in the ZIP with an `"error"` field. This ensures a partial export is
always produced rather than a total failure.

## Configuration

No new settings or env vars. The export uses whichever stores are already
configured for the running deployment (Oracle, SQLite, in-memory).

## Open questions / risks

- Large datasets (many thousands of runs) may cause high memory usage because
  the ZIP is built in-memory. If this becomes a problem, consider streaming
  directly to disk and serving via `FileResponse`.
- The `processes.json` section currently exports *all* processes, not filtered
  by `user_id`, because the `StateStore` interface has no user-scoped list.
  This is acceptable for now (single-user deployment) but must be revisited
  for multi-tenant use.
