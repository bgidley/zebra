# commons-skill-sync Specification

## Purpose
TBD - created by archiving change commons-skill-sync. Update Purpose after archive.

## Requirements

### Requirement: Commons client
The Commons SHALL be reached only through a `CommonsClient` with `publish`, `subscribe` and
`fetch`. An in-memory implementation SHALL exist for tests, and every client SHALL refuse to
publish a `SKILL` event to a relay that is not private. A client for a public relay SHALL also
refuse every event whose kind is not one of the public Commons kinds or that is not tagged
`["t","zebra-commons"]`.

#### Scenario: SKILL refused on a public relay
- **WHEN** a `SKILL` event is published to a non-private relay
- **THEN** publishing raises and the relay stores nothing

#### Scenario: Non-public kind refused on a public relay
- **WHEN** an event of a kind that is not public is published to a non-private relay
- **THEN** publishing raises and the relay stores nothing

### Requirement: SKILL events go only to approved spheres
A `SKILL` event SHALL be built once per certified, unrevoked device of a sphere listed in the
workflow's `share_with`, other than the sender, and never for any other device.

#### Scenario: Home-only share
- **WHEN** a workflow with `share_with: [home]` is sent from a home device
- **THEN** no event is addressed to a work device

### Requirement: SKILL verification
A receiver SHALL accept a `SKILL` only if it is addressed to its own device key, correctly signed
by a device certified by the receiver's own Zebra key and not revoked, its YAML hash equals the
block's `content_sha256` and the `x` tag, the block is not `foreign_users`, and the receiver's
sphere is in the sent `share_with`.

#### Scenario: Tampered YAML
- **WHEN** the YAML in a received event no longer hashes to its block's `content_sha256`
- **THEN** verification fails with `hash_mismatch` and nothing is adopted

### Requirement: Suggest-and-approve sharing
Zebra SHALL propose sharing a workflow with another sphere only after `MIN_RUNS_TO_SHARE` successful
runs or after the dream cycle, and only if it is `commons_exportable`, neither its current version
nor any ancestor has a leak-guard `kept` or `error` result (the writer's status or the save-time
check) and every version in its lineage has a journal `saved` record (unmodified built-ins and the
sent ancestors of a synced version excepted), and the personal-data, confidentiality and
sensitivity checks pass. Every check SHALL fail closed. A successful goal run SHALL check the
run-count trigger when a sync service is configured. Nothing SHALL be sent before the share is approved, and the send SHALL refuse a tainted
version even if approved.

#### Scenario: Not sent until approved
- **WHEN** a home workflow reaches two successful runs
- **THEN** a share task waits for a human and no `SKILL` event exists until it is approved

#### Scenario: Leak-guard taint blocks a share
- **WHEN** the version, or an ancestor it was edited from, was saved with a leak-guard `kept` or
  `error` result, including a save-time `kept` under a writer's own `generalised` record
- **THEN** it is recorded as `blocked`, no share task is raised and no `SKILL` event is sent

#### Scenario: No record of who wrote a version
- **WHEN** a version, or a non-built-in ancestor outside a synced lineage, has no journal `saved`
  record (written before the journal, or the journal was lost)
- **THEN** it is recorded as `blocked` and no `SKILL` event is sent

#### Scenario: Second successful goal run
- **WHEN** `assess_and_record` records a workflow's second successful run on a device with a sync
  service
- **THEN** a *Skill Share* process starts and waits for approval, and a later run does not start
  another for the same version

#### Scenario: A skipped or failed proposal is not waiting
- **WHEN** the share check routes `skip`, or the *Skill Share* process fails
- **THEN** the journal records `skipped` or `failed`, not `proposed`, and Zebra may ask again later

#### Scenario: Codename blocked
- **WHEN** a work workflow contains text matching `SYNC_CONFIDENTIAL_PATTERNS`
- **THEN** it is recorded as blocked and no share task is raised

#### Scenario: Another user's runs
- **WHEN** a workflow's lineage saw another user's runs (`foreign_users`)
- **THEN** it is never proposed

### Requirement: Observed spheres
A workflow the sensitivity check flags SHALL never be proposed to an observed sphere. Sharing with
an observed sphere, or sharing a workflow whose `tainted_by` holds an observed sphere, SHALL need an
`observed_share_approval` human task that no trust level or freeing skips; a share to an observed
sphere SHALL need the "visible on a managed device" confirmation.

#### Scenario: Job search never reaches work
- **WHEN** a home job-application workflow is considered for the observed work sphere
- **THEN** it is recorded as sensitive, no task is raised and nothing is sent

#### Scenario: Freed Zebra still asks
- **WHEN** the owner is freed and a workflow is shared with an observed sphere
- **THEN** the `observed_share_approval` task is still raised

### Requirement: Earned sharing autonomy
For a target that is not observed and a workflow whose `tainted_by` holds no observed sphere,
`trust_gate (sharing)` SHALL decide whether the "Share X with <sphere>?" task is needed.

#### Scenario: Autonomous sharing at home
- **WHEN** the owner's `sharing` level is AUTONOMOUS and a home workflow is shared with another unobserved sphere
- **THEN** the share is approved without a human task

### Requirement: Sync direction
A device SHALL send only when `sync_direction` is `send` or `both` and receive only when it is
`receive` or `both`. The direction SHALL default to `ZEBRA_SYNC_DIRECTION` (`both` when unset; an
unknown value SHALL mean `off`).

#### Scenario: Receive-only device
- **WHEN** a device's direction is `receive`
- **THEN** it proposes and sends nothing

### Requirement: Receive pipeline
A received workflow SHALL be validated (definition valid, every action registered), scanned again
for personal and confidential data, passed through `trust_gate (sharing)` (or a human approval) and
adopted through `WorkflowLibrary.save(writer="adopt")`. Stats SHALL be kept only as a snapshot.

#### Scenario: Approved work workflow appears at home
- **WHEN** a work workflow approved for home is received at home and passes the gates
- **THEN** the home library holds it with the same `content_sha256`

### Requirement: Lineage merge
The receiver SHALL merge by `commons.ancestors`: the same hash is a no-op, a descendant
fast-forwards (the old file retired), an ancestor is ignored, and anything else is a fork saved as
`<name> (from <sphere>)` with `fork_of` on both copies and a choice task.

#### Scenario: Edits on both sides
- **WHEN** both devices change a shared workflow and one is received by the other
- **THEN** both versions exist, both have `fork_of` set and a choice task waits

### Requirement: Lineage-aware lookup and curation
The library's current-file lookup SHALL prefer a descendant over its ancestors and a non-fork over
a fork, and the curator SHALL retire an older same-name copy only when it is an ancestor of the
current copy, never a file with `fork_of`.

#### Scenario: Fork never auto-retired
- **WHEN** the curator runs over a library holding a fork awaiting a choice
- **THEN** neither fork is retired

### Requirement: Share status in the genealogy
The private genealogy SHALL list, for the current version, each other sphere's share status and any
fork awaiting a choice.

#### Scenario: Shared with work
- **WHEN** the current version was approved for work
- **THEN** the genealogy lists work as shared
