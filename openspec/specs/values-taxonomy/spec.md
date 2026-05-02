### Requirement: Field-scoped tag taxonomy

The system SHALL maintain a `Tag` table where each row is scoped to exactly one of four fields: `core_values`, `ethical_positions`, `priorities`, `deal_breakers`. The pair `(field, slug)` SHALL be unique.

#### Scenario: Same slug exists in two fields

- **WHEN** the slug `"family"` is registered as a tag in both the `core_values` and `priorities` fields
- **THEN** both rows coexist and are returned independently when the wizard queries by field

#### Scenario: Duplicate slug within a field is rejected

- **WHEN** a write attempts to insert `(field="core_values", slug="honesty")` while a row with the same pair already exists
- **THEN** the write fails with a uniqueness violation and no second row is created

### Requirement: Three-state tag lifecycle

Each `Tag` SHALL have a `status` that is one of `seeded`, `promoted`, or `candidate`. `seeded` tags are those installed by the bootstrap fixture. `candidate` tags are those proposed by the LLM and confirmed by a user but not yet curated. `promoted` tags are those a curator has elevated to first-class status. Status transitions SHALL be: `candidate → promoted` (manual, out of scope for this change) and `seeded → promoted` is not used (seeded tags are already first-class).

#### Scenario: Bootstrap creates seeded tags

- **WHEN** a fresh database has its data migrations applied
- **THEN** `Tag` rows from the seed fixture exist with `status = "seeded"`

#### Scenario: User-confirmed candidate tag is persisted

- **WHEN** the user confirms a previously unknown tag on the wizard's review step
- **THEN** a `Tag` row is upserted with `status = "candidate"` and `usage_count = 1`, or its `usage_count` is incremented if the row already exists

### Requirement: Approved tag set drives LLM extraction

The `extract_values_tags` task action SHALL retrieve all tags with `status ∈ {seeded, promoted}` for each field and include them in the LLM prompt as the canonical set the model should pick from. The LLM SHALL also be permitted to suggest new tags as candidates.

#### Scenario: Extraction prompt includes approved tags

- **WHEN** `extract_values_tags` runs
- **THEN** the LLM prompt for each field contains the labels of every tag with `status ∈ {seeded, promoted}` for that field

#### Scenario: LLM proposes a new candidate

- **WHEN** the LLM returns a tag in `candidate_tags` that is not present in the approved set
- **THEN** the candidate is presented to the user on the review step and is persisted only if the user confirms it

### Requirement: Review step is the persistence gate

The wizard's review step SHALL display extracted approved tags and proposed candidate tags per field, allow the user to add, remove, or edit tags, and SHALL be the single point at which tags are persisted to the saved version. Tags rejected by the user MUST NOT be persisted on the version.

#### Scenario: User rejects a candidate

- **WHEN** the LLM proposes a candidate tag and the user removes it on the review step
- **THEN** the saved `ValuesProfileVersion` does not include that tag, and no new `Tag` row is created for it

#### Scenario: User adds a tag by hand

- **WHEN** the user types a new tag on the review step that the LLM did not propose
- **THEN** the saved version includes that tag, and a `Tag` row is upserted with `status = "candidate"` and `usage_count = 1` (or incremented)

### Requirement: Bootstrap command produces a reviewable starter taxonomy

The system SHALL ship a `manage.py bootstrap_values_taxonomy` command that calls an LLM to draft a starter taxonomy for all four fields and writes the result to `zebra-agent-web/fixtures/values_taxonomy_seed.yaml`. The command SHALL NOT directly insert rows into the database; review and commit are explicit human steps.

#### Scenario: Running the command produces a fixture file

- **WHEN** a maintainer runs `manage.py bootstrap_values_taxonomy`
- **THEN** the command writes a YAML file at `zebra-agent-web/fixtures/values_taxonomy_seed.yaml` containing tag definitions for all four fields, and prints a message reminding the maintainer to review and commit the file

#### Scenario: Bootstrap is idempotent on re-run

- **WHEN** the command is run a second time on a machine where the fixture already exists
- **THEN** the command refuses to overwrite by default (or writes to a `.new` sibling for diff review), so prior reviewed content is not silently lost

### Requirement: Tag extraction failure does not block the workflow

If the `extract_values_tags` action fails (LLM error, parse error, timeout) it SHALL still return success with empty tag sets, and the workflow SHALL proceed to the review step where the user can fill in tags manually. There SHALL NOT be a separate "failure" branch in the wizard workflow YAML.

#### Scenario: LLM call returns an error

- **WHEN** the underlying LLM call raises an exception during `extract_values_tags`
- **THEN** the action logs the error, returns `TaskResult.ok` with empty `approved_tags` and `candidate_tags` for every field, and the workflow advances to the review step

#### Scenario: User completes save with manual-only tags after extraction failure

- **WHEN** extraction returned empty results and the user enters tags by hand on the review step
- **THEN** the save proceeds normally and persists the user's tags as `candidate` rows
