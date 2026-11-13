## Why

Instances (#279 first boot, #280 updates) must learn what a release is and trust it: which image
digest to pull, from which versions they may update, whether it is breaking or a security fix.
Slice R3 of #283 (part of #275); Refs #283.

## What Changes

- `zebra_agent/release.py`: strict release manifest schema v1 (`version`, `channel`, `image`
  by digest, `digest`, `platforms` incl. `linux/arm64`, `min_from`, `breaking`, `migrations`
  expand/contract, `notes_url`, `notes_md`, `security`, `unsupported_below`, `published_at`) and
  verification of cosign `sign-blob` signatures (signature checked before the schema).
- `scripts/release_manifest.py`: `build` (expand = migrations added since the previous tag,
  `--contract` needs `--breaking`, notes from the GitLab release, security auto from notes),
  `sign` (`cosign sign-blob --tlog-upload=false`), `verify` (in-process, `--cosign` also runs
  `cosign verify-blob`), `promote` (verified release → `channels/stable.json` only), `publish` /
  `fetch` (oci CLI; unsigned files refused).
- `.gitlab-ci.yml`: `release:manifest` (auto) and `release:promote-stable` (manual) on `vX.Y.Z`
  tag pipelines only, and only when `RELEASE_BUCKET` and `COSIGN_PRIVATE_KEY` exist.
- `cryptography` becomes a direct dependency of `zebra-agent` (already locked transitively).

## Non-goals

Publishing the image (R2), creating the key pair, bucket or `v*` tag protection (owner
credentials), retention, the #279 stack zip scan, the updater (#280). Prod deploy is unchanged.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `release-pipeline`: adds signed release manifests and channels.

## Impact

`zebra-agent` (new module, dependency), `scripts/`, `.gitlab-ci.yml`, docs. No data model change.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | A manifest is accepted only when it matches schema v1 | `TestSchema` (each rule, unknown fields, contract ⇒ breaking, digest pinned) |
| O2 | Any tampered byte, missing signature or other key fails verification, and an unsigned file is never published | `TestSignatures`, `test_tampered_file_fails_verify`, `test_publish_refuses_unsigned` |
| O3 | Promoting to stable changes only the channel file and its signature | `test_promote_changes_only_the_channel_file`; a tampered release cannot be promoted |
| O4 | The new jobs exist only on configured release tag pipelines; master pipelines and prod deploy are unaffected | `TestCiJobs`; `glab ci lint`; master pipeline green with no new jobs |
