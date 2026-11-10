# release-pipeline Specification

## Purpose
Semver releases cut from green master, the running version, release notes and signed release manifests (#283).

## Requirements

### Requirement: Release version in version metadata
`scripts/gen_version.py` SHALL write a `version` key derived from the newest `vX.Y.Z` tag
reachable from HEAD: `X.Y.Z` on the tag, `X.Y.Z+N.g<hash>` N commits after it, and
`0.0.0+g<hash>` when no release tag exists. `GET /api/version/` SHALL return it, and the version
footer SHALL show `vX.Y.Z` (with `+N` after the tag) once a release tag exists.

#### Scenario: On a release tag
- **WHEN** HEAD is tagged `v0.3.0`
- **THEN** `version.json` has `"version": "0.3.0"`

#### Scenario: After a release tag
- **WHEN** HEAD is four commits after `v0.3.0`
- **THEN** `version` is `0.3.0+4.g<short hash>` and the footer shows `v0.3.0+4`

#### Scenario: Before the first release
- **WHEN** no `vX.Y.Z` tag exists
- **THEN** `version` is `0.0.0+g<short hash>` and the footer shows only the hash

### Requirement: Release tags only from green master
The `release:tag` CI job SHALL be manual, exist only on master push pipelines, and sit in the
last stage. `scripts/release_tag.py` SHALL refuse (exit 1, nothing created) when the pipeline is
not a master push, when the ref is no longer the head of master, when the tag already exists or
when no token is configured.

#### Scenario: Green master
- **WHEN** the owner runs `release:tag` on the current master head after smoke passed
- **THEN** a GitLab release and tag `vX.Y.Z` are created at that commit, `X.Y.Z` being the next
  minor version unless `RELEASE_BUMP` or `RELEASE_VERSION` says otherwise

#### Scenario: Stale pipeline
- **WHEN** the job is run from an older master pipeline
- **THEN** it refuses with "no longer the head of master"

#### Scenario: Feature branch
- **WHEN** the script runs on any other branch or pipeline source
- **THEN** it refuses and creates nothing

### Requirement: Release notes from closed issues
Release notes SHALL list the issues closed by commits since the previous release tag (`Closes`,
`Fixes`, `Resolves #N`), each with its title, omitting issues GitLab reports as still open, with
issues labelled `security` in a Security section before the others.

#### Scenario: Mixed issues
- **WHEN** commits since `v0.2.0` close #10 and #12 (labelled `security`) and #13 is still open
- **THEN** the notes list #12 under Security, #10 under Closed issues, and omit #13
