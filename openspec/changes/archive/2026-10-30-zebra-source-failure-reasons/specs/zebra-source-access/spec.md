## ADDED Requirements

### Requirement: Source access failures carry a reason

Every failed `zebra_source` request SHALL fail the task with an error that starts with
`[<reason>] `, where `<reason>` is one of `protected`, `not_deployed`, `missing`, `invalid` or
`error`, and that ends with the list/search recovery hint.

#### Scenario: Protected path
- **WHEN** a caller reads a hidden, secret or runtime file, a path outside the source tree, or an
  existing top-level entry that is not allowlisted
- **THEN** the task fails with an error starting `[protected] `

#### Scenario: Path not deployed
- **WHEN** a caller reads or lists a path under an allowlisted top-level entry that is absent from
  the deployed tree
- **THEN** the task fails with an error starting `[not_deployed] `

#### Scenario: Missing path
- **WHEN** a caller reads or lists a path that does not exist and has no single clear match
- **THEN** the task fails with an error starting `[missing] `

#### Scenario: Bad request
- **WHEN** a caller gives no path or pattern, an invalid regex, a glob leaving the tree, a
  directory to read, a file to list, or a file over the size cap
- **THEN** the task fails with an error starting `[invalid] `

#### Scenario: Read error
- **WHEN** reading a file raises an `OSError`
- **THEN** the task fails with an error starting `[error] ` instead of raising
