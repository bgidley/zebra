## Context

R1 cuts `vX.Y.Z` tags. R2 (not built) will push the arm64 image to a public registry and sign
it. R3 describes each release in a signed manifest per channel that #279 and #280 read. The plan
(cosign key-based signing, public Object Storage bucket, expand/contract migrations) is in
`specs/release-pipeline-design.md`.

## Decisions

- **cosign key, not Commons keys**: Commons keys are per-Zebra identities, not a project key.
  Key-based (not keyless) so verification is offline: no Fulcio/Rekor, `--tlog-upload=false`.
- **Verify in Python with `cryptography`**: cosign `sign-blob` with a key is base64 of a DER
  ECDSA P-256 signature over SHA-256 of the bytes; the cosign public key is PEM SPKI. So
  `verify_blob` needs no cosign binary on an instance; `--cosign` cross-checks in CI.
- **Signature before parsing**: `load_verified` never parses or validates unsigned bytes.
- **Strict schema**: unknown keys are refused; a new field is a schema bump.
- **Channel file = manifest copy** with `channel` set, signed separately, so promotion writes
  only `channels/<to>.json(.sig)` and never touches `releases/`.
- **Dormant CI**: jobs gated on `$RELEASE_BUCKET && $COSIGN_PRIVATE_KEY` and a semver tag, so
  nothing appears until the owner configures them; `RELEASE_IMAGE` comes from R2 by dotenv.

## Interfaces

`zebra_agent.release` (`validate_manifest`, `manifest_errors`, `verify_blob`, `load_verified`,
`dump_manifest`, `sign_blob`, `parse_version`, `ManifestError`); `scripts/release_manifest.py`
subcommands; CI jobs `release:manifest`, `release:promote-stable`. No data model or setting
changes. `specs/zebra-as-is.md`: Releases subsection.

## Risks

- Not cross-checked against a real cosign binary (none on the host); R2 installs cosign and the
  first tag run's `verify --cosign` is the check.
- Upload order (file, then `.sig`) leaves a moment where the pair mismatches; readers fail
  closed and retry.
