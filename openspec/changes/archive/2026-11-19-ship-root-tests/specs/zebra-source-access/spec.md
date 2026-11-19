## ADDED Requirements

### Requirement: Root tests are readable
`zebra_source` SHALL allow the repo-root `tests/` directory, and the prod image SHALL ship it, so
a review can cite a root test file as evidence.

#### Scenario: Read a root test file
- **WHEN** a caller reads `tests/iac/test_scan.py` and the file exists in the source root
- **THEN** the task succeeds and returns its text

#### Scenario: Image ships the allowlist
- **WHEN** the `Dockerfile` runtime stage is inspected
- **THEN** it copies `tests/` alongside the other allowlisted top-level directories
