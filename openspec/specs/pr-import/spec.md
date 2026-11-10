# pr-import Specification

## Purpose
TBD - created by archiving change maintainer-pr-import. Update Purpose after archive.

## Requirements

### Requirement: Import stops before CI
The import script SHALL NOT push to GitLab until the maintainer supplies the reviewed head sha.

#### Scenario: prepare pushes nothing
- **WHEN** the maintainer runs `prepare` on a clean signed PR
- **THEN** a local branch exists and the GitLab remote has no new branch

#### Scenario: PR changed after review
- **WHEN** `push` is given a sha that is not the current PR head
- **THEN** the import is refused and nothing is pushed

### Requirement: Origin statement and scan are enforced
The script SHALL refuse a PR whose Zebra-origin statement is missing, malformed, for another head or
repo, or badly signed (unless `--allow-unsigned`), and a PR whose diff scan is not clean or fails.

#### Scenario: rejected diff
- **WHEN** the diff adds a `.env` file or a secret
- **THEN** `prepare` is refused and creates no branch

### Requirement: Contributor authorship preserved
The pushed branch SHALL contain the contributor's commits unchanged.

#### Scenario: author kept
- **WHEN** `push` succeeds
- **THEN** the pushed commit has the contributor's author
