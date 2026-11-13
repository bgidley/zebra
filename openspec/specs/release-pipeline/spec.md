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

### Requirement: Release manifest schema v1
A release manifest SHALL be a JSON object with exactly the keys `schema` (1), `version`,
`channel` (`stable`, `next` or `test`), `image` (`registry/repo@sha256:<64 hex>`), `digest`
(equal to the image's), `platforms` (including `linux/arm64`), `min_from` (≤ `version`),
`breaking`, `migrations` (`expand` and `contract` lists of `app.0001_name`), `notes_url` (https
or empty), `notes_md`, `security`, `unsupported_below` (≤ `version` or null) and `published_at`
(UTC, ending in `Z`). A manifest with contract migrations SHALL be `breaking`.

#### Scenario: Image by tag
- **WHEN** `image` names a tag instead of a digest
- **THEN** validation fails

#### Scenario: Contract without breaking
- **WHEN** `migrations.contract` is non-empty and `breaking` is false
- **THEN** validation fails

### Requirement: Manifests are signed and verified
Every published manifest file SHALL have a cosign `sign-blob` signature beside it
(`<file>.sig`). Verification SHALL check the signature against the project public key before
parsing, then validate the schema. Publishing SHALL refuse a file without its signature.

#### Scenario: Tampered byte
- **WHEN** any byte of a signed manifest changes
- **THEN** verification fails

#### Scenario: Other key
- **WHEN** a manifest is signed with a key other than the project key
- **THEN** verification fails

### Requirement: Channels and promotion
The tag pipeline SHALL write `releases/vX.Y.Z.json` and `channels/next.json`. Promotion to
`stable` SHALL verify the release manifest and write only `channels/stable.json` and its
signature. The manifest CI jobs SHALL run only on `vX.Y.Z` tag pipelines with the release
bucket and signing key configured, promotion only manually.

#### Scenario: Promote
- **WHEN** the owner runs `release:promote-stable` on tag `v0.3.0`
- **THEN** `channels/stable.json` equals `releases/v0.3.0.json` with `channel` `stable`, and no
  other file changes

#### Scenario: Master pipeline
- **WHEN** a master push pipeline runs
- **THEN** neither manifest job is created
