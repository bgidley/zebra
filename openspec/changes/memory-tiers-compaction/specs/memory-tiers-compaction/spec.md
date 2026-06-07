## ADDED Requirements

### Requirement: Memory entries carry a tier field
`WorkflowMemoryEntry` and `ConceptualMemoryEntry` SHALL each carry a `tier` field
(`"hot"`, `"warm"`, or `"cold"`) that records the last-applied compaction tier.
New entries SHALL default to `"hot"`. The field SHALL be persisted to the database.

#### Scenario: New entry defaults to hot
- **WHEN** a new `WorkflowMemoryEntry` or `ConceptualMemoryEntry` is created
- **THEN** its `tier` field is `"hot"`

#### Scenario: Tier persisted across restarts
- **WHEN** a compaction run updates an entry's tier to `"warm"`
- **THEN** subsequent reads of that entry return `tier == "warm"`

### Requirement: MemoryStore exposes entries needing compaction
The `MemoryStore` interface SHALL provide `get_entries_for_compaction(now: datetime)`
that returns a `CompactionBatch` containing only entries whose current tier is staler
than their age warrants (i.e. entries that have crossed a tier boundary since the
last compaction). All implementations MUST implement this method.

#### Scenario: Entry crosses warm boundary
- **WHEN** a `WorkflowMemoryEntry` has `timestamp` older than 2 weeks and `tier == "hot"`
- **THEN** it appears in `CompactionBatch.warm_workflow`

#### Scenario: Entry crosses cold boundary
- **WHEN** a `WorkflowMemoryEntry` has `timestamp` older than 2 months and `tier` is not `"cold"`
- **THEN** it appears in `CompactionBatch.cold_workflow`

#### Scenario: Already-compacted entry excluded
- **WHEN** an entry's current `tier` matches its age-appropriate tier
- **THEN** it does NOT appear in the compaction batch

### Requirement: Warm WorkflowMemoryEntry is LLM-compressed
When a `WorkflowMemoryEntry` transitions to warm, the system SHALL use an LLM call to
compress `output_summary` and `effectiveness_notes` into a single digest of at most
150 tokens. The compressed text SHALL replace both fields. The `tier` field SHALL be
updated to `"warm"`.

#### Scenario: Warm compression runs
- **WHEN** a `WorkflowMemoryEntry` is in `CompactionBatch.warm_workflow`
- **THEN** an LLM call produces a compressed digest, both text fields are updated, and `tier` becomes `"warm"`

#### Scenario: LLM failure degrades gracefully
- **WHEN** the LLM call raises an exception during warm compression
- **THEN** the entry is left unchanged, a warning is logged, and compaction continues with remaining entries

### Requirement: Cold WorkflowMemoryEntry is stripped to metadata
When a `WorkflowMemoryEntry` transitions to cold, the system SHALL clear
`output_summary` and `effectiveness_notes` (set to empty string) and update
`tier` to `"cold"`. All other fields (id, workflow_name, goal truncated to 200 chars,
success, timestamp, run_id, rating, user_feedback) SHALL be retained.

#### Scenario: Cold stripping runs
- **WHEN** a `WorkflowMemoryEntry` is in `CompactionBatch.cold_workflow`
- **THEN** `output_summary` and `effectiveness_notes` are cleared and `tier` becomes `"cold"`

### Requirement: Warm ConceptualMemoryEntry is trimmed and compressed
When a `ConceptualMemoryEntry` transitions to warm, the system SHALL trim
`recommended_workflows` to the top 3 entries by `use_count` and SHALL use an LLM
call to compress `anti_patterns` to at most 100 tokens. The `tier` field SHALL be
updated to `"warm"`.

#### Scenario: Warm conceptual compaction runs
- **WHEN** a `ConceptualMemoryEntry` is in `CompactionBatch.warm_conceptual`
- **THEN** `recommended_workflows` has at most 3 entries (highest use_count), `anti_patterns` is compressed, and `tier` becomes `"warm"`

### Requirement: Cold ConceptualMemoryEntry is stripped to top workflow
When a `ConceptualMemoryEntry` transitions to cold, the system SHALL trim
`recommended_workflows` to the single entry with the highest `use_count` and SHALL
clear `anti_patterns`. The `tier` field SHALL be updated to `"cold"`.

#### Scenario: Cold conceptual stripping runs
- **WHEN** a `ConceptualMemoryEntry` is in `CompactionBatch.cold_conceptual`
- **THEN** `recommended_workflows` has exactly 1 entry and `anti_patterns` is empty and `tier` becomes `"cold"`

### Requirement: Compaction runs automatically every 6 hours in the deployed service
The system SHALL schedule a compaction run every 6 hours via the existing routine
scheduler (`fixtures/routines/compact_memory.yaml`). The routine SHALL be
`budget_aware: false` so it runs regardless of daily budget state.

#### Scenario: Routine fires on schedule
- **WHEN** 6 hours have elapsed since the last compaction run
- **THEN** the `"Compact Memory"` workflow is triggered by the scheduler

#### Scenario: Service restart does not skip compaction
- **WHEN** the service restarts and the scheduled time has already passed
- **THEN** `on_missed: run` ensures the compaction fires on next daemon startup

### Requirement: Compaction is manually triggerable
The system SHALL provide a `python manage.py compact_memory` management command that
runs one compaction pass synchronously and exits.

#### Scenario: Manual compaction command
- **WHEN** `python manage.py compact_memory` is run
- **THEN** all entries needing compaction are processed and the command exits 0
