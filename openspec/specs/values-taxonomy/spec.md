# values-taxonomy Specification

## Purpose
The field-scoped values-tag taxonomy behind the values profile (F18): tag lifecycle, curation, how approved tags anchor LLM extraction, and bootstrap.

## Requirements

### Requirement: Field-scoped tag taxonomy

The system SHALL maintain a `Tag` table where each row is scoped to exactly one of four fields: `core_values`, `ethical_positions`, `priorities`, `deal_breakers`. The pair `(field, slug)` SHALL be unique.

#### Scenario: Same slug exists in two fields

- **WHEN** the slug `"family"` is registered as a tag in both the `core_values` and `priorities` fields
- **THEN** both rows coexist and are returned independently when the wizard queries by field

#### Scenario: Duplicate slug within a field is rejected

- **WHEN** a write attempts to insert `(field="core_values", slug="honesty")` while a row with the same pair already exists
- **THEN** the write fails with a uniqueness violation and no second row is created

### Requirement: Three-state tag lifecycle

Each `Tag` SHALL have a `status` that is one of `seeded`, `promoted`, `candidate`, `rejected`, or `merged`. The statuses mean:

- `seeded`: installed by the bootstrap fixture.
- `candidate`: proposed by the LLM and confirmed by a user, but not yet curated.
- `promoted`: elevated by a curator to first-class status.
- `rejected`: declined or archived by a curator.
- `merged`: folded into another tag in the same field, which `merged_into` records.

The curator transitions SHALL be `candidate|rejected → promoted`, `candidate|promoted → rejected`, `promoted → candidate`, and `candidate|promoted|rejected → merged`. The status of a `seeded` tag SHALL NOT change.

#### Scenario: Bootstrap creates seeded tags

- **WHEN** a fresh database has its data migrations applied
- **THEN** `Tag` rows from the seed fixture exist with `status = "seeded"`

#### Scenario: User-confirmed candidate tag is persisted

- **WHEN** the user confirms a previously unknown tag on the wizard's review step
- **THEN** a `Tag` row is upserted with `status = "candidate"` and `usage_count = 1`, or its `usage_count` is incremented if the row already exists

#### Scenario: Seeded tag cannot be curated

- **WHEN** a curator attempts to promote, reject, demote, or merge away a `seeded` tag
- **THEN** the operation fails with an error and the row is unchanged

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

### Requirement: Curator can promote, reject and demote tags

The system SHALL provide curator operations through both `manage.py values_taxonomy` and the `/profile/taxonomy/` page. Each operation changes a tag's status according to the lifecycle transitions. Promoting SHALL set `promoted_at`, and demoting SHALL clear it. A promoted tag SHALL be included in the approved set that `extract_values_tags` uses. A rejected or demoted tag SHALL NOT be included.

#### Scenario: Promoted candidate anchors future extraction

- **WHEN** a curator promotes candidate `(core_values, curiosity)`
- **THEN** its status becomes `promoted`, `promoted_at` is set, and `get_approved_tags("core_values")` includes `curiosity`

#### Scenario: Rejected tag stays rejected when confirmed again

- **WHEN** a curator rejects candidate `(priorities, gaming)` and a user later confirms `gaming` again
- **THEN** the row remains `rejected` with its `usage_count` incremented, and it is not in the approved set

#### Scenario: Invalid transition is refused

- **WHEN** a curator attempts to demote a `candidate` tag
- **THEN** the operation fails with an error message and the row is unchanged

### Requirement: Curator can merge duplicate tags

The system SHALL allow a source tag to be merged into a target tag in the same field. The merge SHALL:

- add the source's `usage_count` to the target;
- set the source to `merged`, with `merged_into` set to the target slug and `usage_count` set to 0;
- repoint any tags previously merged into the source to the target.

Later confirmations of the source slug SHALL increment the target, not the source.

#### Scenario: Merge candidate into seeded tag

- **WHEN** candidate `(core_values, truthfulness)` with usage 4 is merged into seeded `(core_values, honesty)` with usage 2
- **THEN** `honesty` has usage 6 and `truthfulness` is `merged` into `honesty` with usage 0

#### Scenario: Confirmation of merged slug counts toward target

- **WHEN** a user confirms `truthfulness` after it was merged into `honesty`
- **THEN** `honesty.usage_count` is incremented and `truthfulness` is unchanged

#### Scenario: Invalid merge is refused

- **WHEN** a curator merges a tag into itself, into a missing slug, or into a `merged` or `rejected` target
- **THEN** the operation fails and no rows change

### Requirement: Promotion suggestions by usage threshold

The system SHALL flag each `candidate` tag whose `usage_count` is greater than or equal to `VALUES_TAG_PROMOTION_THRESHOLD` (default 3) as suggested for promotion. The system SHALL NOT promote these tags automatically.

#### Scenario: Frequently confirmed candidate is suggested

- **WHEN** a candidate has `usage_count = 3` and the threshold is 3
- **THEN** the curator page and `values_taxonomy list --suggested` mark it as suggested, and its status remains `candidate`

### Requirement: Stale candidate pruning

`manage.py values_taxonomy prune` SHALL delete `candidate` rows that are older than `--days` (default 90) and have `usage_count <= --max-usage` (default 1). With `--dry-run`, the command SHALL report which rows it would delete without deleting them. Rows in any other status SHALL NOT be pruned.

#### Scenario: Dry run deletes nothing

- **WHEN** `prune --dry-run` runs with one stale single-use candidate present
- **THEN** the command reports one tag and the row still exists

#### Scenario: Prune removes only stale low-usage candidates

- **WHEN** `prune` runs with a stale single-use candidate, a fresh candidate, a stale candidate with usage 5, and a stale rejected tag
- **THEN** only the stale single-use candidate is deleted
