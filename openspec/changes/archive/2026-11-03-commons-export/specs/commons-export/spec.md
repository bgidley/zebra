## ADDED Requirements

### Requirement: Content-hash definition ids
The definition loader SHALL derive a workflow's definition id from its `commons` block when the
block holds a `content_sha256`: `c:` + sha256(`content_sha256` + `:` + `name`)[:16]. A workflow
without a block SHALL keep the `sha256(name:version)` id.

#### Scenario: Same name and version, different content
- **WHEN** two stamped workflows share a name and version but differ in content
- **THEN** their definition ids differ and both start with `c:`

#### Scenario: Legacy file
- **WHEN** a workflow file has no `commons` block
- **THEN** it loads with its `sha256(name:version)` id

### Requirement: Signed export file
Exporting a workflow SHALL produce a file holding an event signed by this deployment's device
key, carrying the YAML without the block or local tags, the `commons` block and the content hash,
together with the `DEVICE_CERT` chain attributing it to the Zebra. Export SHALL be refused unless
`commons_exportable()` is true and the device is certified.

#### Scenario: Export refused for a non-exportable workflow
- **WHEN** a workflow tagged `system`, with `foreign_users: true` or with no block is exported
- **THEN** export fails with a reason and no file is produced

### Requirement: Export verification
Verification SHALL accept a file only if it parses, its event id and signature are valid, its
signer is the declared Zebra or a device with a valid unrevoked cert from it, the hash in the
`x` tag equals the block's `content_sha256` and the hash recomputed from the YAML, and the block's
`foreign_users` is `false`.

#### Scenario: Exported file verifies
- **WHEN** an exportable workflow is exported and the file is verified
- **THEN** verification succeeds and names the Zebra

#### Scenario: One tampered byte
- **WHEN** any single byte of the exported file is changed
- **THEN** verification fails

#### Scenario: Revoked device
- **WHEN** the verifier holds a `DEVICE_REVOKE` for the signing device
- **THEN** verification fails with reason `revoked`

### Requirement: Adoption keeps the received block
`WorkflowLibrary.save(writer="adopt")` SHALL verify that the YAML's hash equals the received
block's `content_sha256` and the offered or sent hash, and SHALL keep the block verbatim except
the local `name`, `sphere`, `share_with` (`[]`), `adopted_at`, `supervised` (`true`) and an
absent `origin_pubkey`. It SHALL never add the `llm-defined` tag, and SHALL refuse a name already
taken by a different workflow.

#### Scenario: Adopt an export
- **WHEN** a verified export is adopted under a new display name
- **THEN** the saved file has the same `content_sha256` and lineage, `supervised: true`,
  `share_with: []`, no `llm-defined` tag and a `c:` definition id

#### Scenario: Hash mismatch
- **WHEN** the YAML's hash differs from the received block or the offered hash
- **THEN** nothing is saved and the save raises an error

### Requirement: Owner-governed sharing trust domain
`sharing` SHALL be a trust domain with the usual levels. A trust gate on `sharing` SHALL read
the Commons owner's level, whatever user the process runs for, and SHALL route `approve` when the
owner cannot be determined.

#### Scenario: Non-owner process
- **WHEN** the owner's `sharing` level is AUTONOMOUS and a process for another user hits a
  `sharing` trust gate
- **THEN** the gate routes `proceed` based on the owner's level

#### Scenario: Unknown owner
- **WHEN** no Commons owner can be resolved
- **THEN** the `sharing` gate routes `approve`

### Requirement: Personal-data scan fails closed
`commons_pii_scan` SHALL scan every string of the workflow (prompts, defaults, examples) and the
golden tasks with rules and a low-tier LLM, route `clean` only when both find nothing, and route
`rejected` when either finds personal data or the scan cannot complete.

#### Scenario: Email in a default
- **WHEN** a workflow default holds `jane.doe@gmail.com`
- **THEN** the scan routes `rejected` with a rule finding, without needing the LLM

#### Scenario: LLM unavailable
- **WHEN** the rules find nothing but the LLM call fails
- **THEN** the scan routes `rejected` with `failed_closed: true`
