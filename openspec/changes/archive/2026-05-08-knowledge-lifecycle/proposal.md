## Why

The personal knowledge store (F31) persists facts but treats them as static — there is no decay, no verification loop, and no handling when new information contradicts what's already stored. Without lifecycle management, the agent's knowledge silently goes stale and contradictions are silently overwritten, degrading trust. Closes #32.

## What Changes

- Add `deleted_at` and `time_sensitive` fields to `KnowledgeEntry`; soft-delete replaces hard-delete
- Add per-category decay half-life configuration
- Add `decay_confidence` task action that reduces confidence for time-sensitive entries based on half-life
- Add `knowledge_verification` workflow that surfaces low-confidence entries for human confirmation
- Add contradiction detection in `add_entry` / `update_entry` — if a new value conflicts with an existing entry, trigger a `resolve_contradiction` dilemma workflow instead of overwriting
- Store interface gains `soft_delete_entry`, `get_entries_for_verification`, and `find_contradicting_entry` methods
- Scheduled routines (daily decay, weekly verification) registered as `zebra.schedules` entry points

## Capabilities

### New Capabilities
- `knowledge-lifecycle`: Confidence decay, periodic verification prompts, contradiction detection and dilemma escalation, soft-delete for knowledge entries

### Modified Capabilities
- `personal-knowledge-store`: Store interface and `KnowledgeEntry` model gain lifecycle fields (`deleted_at`, `time_sensitive`) and new query methods (`soft_delete_entry`, `get_entries_for_verification`, `find_contradicting_entry`)

## Non-goals

- Cross-domain access (REQ-MEM-006) — separate issue
- Multi-user privacy boundaries — out of scope
- Automatic merging of contradicting entries without human confirmation

## Impact

- `zebra-agent/zebra_agent/knowledge.py` — new fields on `KnowledgeEntry`
- `zebra-agent/zebra_agent/storage/interfaces.py` — new methods on `PersonalKnowledgeStore`
- `zebra-agent/zebra_agent/storage/memory.py` and Django ORM store — implement new methods
- New Django migration for `deleted_at` / `time_sensitive` columns
- New task actions in `zebra-tasks/` — `decay_confidence`, `knowledge_verification`, `resolve_contradiction_knowledge`
- New workflow YAML files in `zebra-agent/` — `knowledge_verification.yaml`, `resolve_contradiction.yaml`
- New scheduler routines registered as `zebra.schedules` entry points
