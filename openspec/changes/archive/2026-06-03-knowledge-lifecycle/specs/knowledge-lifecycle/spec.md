## ADDED Requirements

### Requirement: Confidence decay for time-sensitive entries
The system SHALL provide a `decay_confidence` task action that, for each `time_sensitive=True` knowledge entry belonging to a given user, reduces `confidence` according to the exponential half-life formula `new_confidence = confidence * 0.5 ^ (days_since_verified / half_life_days)`, floored at `0.1`. Only entries with `time_sensitive=True` are processed. The half-life in days is looked up from `CATEGORY_DECAY_HALF_LIFE_DAYS`; if the category has `None` as its half-life (e.g., `history`), the entry is skipped.

#### Scenario: Time-sensitive entry confidence decayed
- **WHEN** `decay_confidence` runs for a user with a `time_sensitive=True` fact entry last verified 365 days ago (half-life 365 days)
- **THEN** the entry's `confidence` is updated to approximately `0.5` of its original value

#### Scenario: Non-time-sensitive entry skipped
- **WHEN** `decay_confidence` runs and an entry has `time_sensitive=False`
- **THEN** the entry's `confidence` is unchanged

#### Scenario: Confidence not decayed below floor
- **WHEN** decay would reduce confidence below `0.1`
- **THEN** confidence is set to `0.1` and not lower

#### Scenario: History category skipped
- **WHEN** `decay_confidence` runs for an entry with `category="history"`
- **THEN** the entry's `confidence` is unchanged (half-life is `None`)

### Requirement: Knowledge verification workflow
The system SHALL provide a `knowledge_verification.yaml` workflow with a corresponding `pick_entries_for_verification` task action. The action reads entries for a user where `confidence < 0.6` OR `last_verified` is older than `verification_age_days` (default 90), limited to `max_entries` (default 5). For each selected entry, a human task presents the key-value pair with options: "Still correct", "Update value", or "Delete". The user's choice is applied: no change, `update_entry`, or `soft_delete_entry`.

#### Scenario: Low-confidence entries selected for verification
- **WHEN** `pick_entries_for_verification` runs for a user with 3 entries below confidence 0.6
- **THEN** the action returns those entries (up to `max_entries`)

#### Scenario: Aged entries selected for verification
- **WHEN** an entry has `confidence >= 0.6` but `last_verified` is older than `verification_age_days`
- **THEN** the entry is included in the verification set

#### Scenario: User confirms entry still correct
- **WHEN** the human task response is "still_correct" for an entry
- **THEN** the entry's `last_verified` is updated to now and `confidence` is set to `1.0`

#### Scenario: User updates entry value
- **WHEN** the human task response is "update" with a new value
- **THEN** `update_entry` is called with the new value and `confidence` reset to `1.0`

#### Scenario: User deletes entry
- **WHEN** the human task response is "delete"
- **THEN** `soft_delete_entry` is called for that entry

#### Scenario: No entries to verify
- **WHEN** all entries have high confidence and are recently verified
- **THEN** the workflow completes immediately with output `{verified: 0, updated: 0, deleted: 0}`

### Requirement: add_knowledge task action with contradiction detection
The system SHALL provide an `add_knowledge` task action that reads `user_id` from `__user_id__`, and `category`, `key`, `value`, `time_sensitive` (default `False`) from task properties. Before storing, it calls `find_contradicting_entry(user_id, category, key)`. If a non-deleted entry with the same `category` and `key` but a different `value` already exists, the action returns `TaskResult.ok(next_route="contradiction", output={existing_id: ..., existing_value: ..., proposed_value: ...})`. If no contradiction, it calls `add_entry` and returns `TaskResult.ok(next_route="stored")`.

#### Scenario: New entry stored when no contradiction
- **WHEN** `add_knowledge` runs for a key that does not exist in the store
- **THEN** the entry is added and `next_route` is `"stored"`

#### Scenario: Identical value is not a contradiction
- **WHEN** `add_knowledge` is called with the same `key` and same `value` as an existing entry
- **THEN** the existing entry is updated (`last_verified` refreshed) and `next_route` is `"stored"`

#### Scenario: Contradicting value triggers escalation route
- **WHEN** `add_knowledge` is called with a `key` that exists with a different `value`
- **THEN** `next_route` is `"contradiction"` and the output contains `existing_value` and `proposed_value`

#### Scenario: Graceful degradation when no store
- **WHEN** `__knowledge_store__` is absent from `context.extras`
- **THEN** the action returns `TaskResult.ok(next_route="stored")` without raising

### Requirement: resolve_contradiction workflow
The system SHALL provide a `resolve_contradiction.yaml` workflow that presents a human task showing the `existing_value` and `proposed_value` for a conflicting knowledge entry. The user chooses: "Keep existing", "Use new value", or "Keep both". The workflow applies the choice: no change, `update_entry` with the new value, or `add_entry` with a new unique key suffixed `_alt`.

#### Scenario: User keeps existing value
- **WHEN** the human task response is "keep_existing"
- **THEN** the store is not modified and the workflow completes with `{resolution: "kept_existing"}`

#### Scenario: User accepts new value
- **WHEN** the human task response is "use_new"
- **THEN** `update_entry` is called with the proposed value and `{resolution: "updated"}`

#### Scenario: User keeps both
- **WHEN** the human task response is "keep_both"
- **THEN** `add_entry` is called with key suffixed `_alt` and `{resolution: "kept_both"}`

### Requirement: Scheduled lifecycle routines registered as entry points
The system SHALL register two scheduler routines under the `zebra.schedules` entry point group in `zebra-agent/pyproject.toml`:
- `knowledge_decay_daily`: schedule `every: 1d`, workflow `knowledge_decay.yaml`
- `knowledge_verification_weekly`: schedule `every: 7d`, workflow `knowledge_verification.yaml`

#### Scenario: Decay routine discovered by scheduler
- **WHEN** the `RoutineRegistry` loads `zebra.schedules` entry points
- **THEN** `knowledge_decay_daily` appears in the discovered routines list

#### Scenario: Verification routine discovered by scheduler
- **WHEN** the `RoutineRegistry` loads `zebra.schedules` entry points
- **THEN** `knowledge_verification_weekly` appears in the discovered routines list
