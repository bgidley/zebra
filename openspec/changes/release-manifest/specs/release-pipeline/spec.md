## ADDED Requirements

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
