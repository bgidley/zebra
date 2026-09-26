## MODIFIED Requirements

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

## ADDED Requirements

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
