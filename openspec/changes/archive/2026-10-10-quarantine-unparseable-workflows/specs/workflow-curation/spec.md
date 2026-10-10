## ADDED Requirements

### Requirement: Unparseable library workflows are retired
The workflow library SHALL move any active `*.yaml` file that does not parse, or is not a mapping, to
`retired/` as a parseable stub. The stub SHALL keep the raw text and record the reason
`unparseable: <error>`. The library SHALL log this once and SHALL NOT re-parse the file on later
loads. Built-in workflow directories SHALL NOT be scanned.

#### Scenario: Truncated workflow in the library
- **WHEN** the library is listed and contains a truncated workflow file
- **THEN** the file is moved to `retired/<stem>.unparseable.yaml` with its raw text kept
- **AND** valid workflows are still listed and loadable

#### Scenario: Shown as retired
- **WHEN** retired workflows are listed after an unparseable file was moved
- **THEN** it appears as `<name> [unparseable]` with reason starting `unparseable:`

#### Scenario: Later loads
- **WHEN** the library is loaded again
- **THEN** no parse error is logged for the moved file

#### Scenario: Not restorable
- **WHEN** a user restores an unparseable stub
- **THEN** the restore is refused with an explanation

### Requirement: The library refuses unparseable workflows
`add_workflow` SHALL raise `ValueError` for YAML that does not parse or is not a mapping, and SHALL
write nothing.

#### Scenario: Truncated YAML added
- **WHEN** `add_workflow` is called with truncated YAML
- **THEN** it raises `ValueError` and no file is written
