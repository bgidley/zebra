## Why

There is no release artifact users could install or update from: no release tags, and the only
version shown is a commit hash. The release pipeline (#283, part of #275) starts with a version
and a way to cut a tag from a known-good master. Slice R1 of #283; Refs #283.

## What Changes

- `scripts/gen_version.py` adds `version` to `version.json`, from the newest `vX.Y.Z` tag:
  `0.3.0` on the tag, `0.3.0+4.gabc1234` after it, `0.0.0+g<hash>` before the first release.
  A shallow CI clone without tags is deepened once (best effort).
- `/api/version/` returns it; the footer shows `v0.3.0` (`v0.3.0+4` after the tag) next to the
  hash once a release exists, with the full version as the tooltip.
- `scripts/release_tag.py` picks the next version (`RELEASE_BUMP` major/minor/patch, default
  minor, or `RELEASE_VERSION`), lists the issues closed by commits since the last tag (`Closes`,
  `Fixes`, `Resolves`; kept only if GitLab says closed; `security` label first) and creates the
  GitLab release, which creates the tag. `--dry-run` changes nothing and needs no token.
- `.gitlab-ci.yml`: new last stage `release` with a manual `release:tag` job on master push
  pipelines only (`allow_failure`), so it can start only after deploy and smoke are green.
  Needs the masked, protected `RELEASE_GITLAB_TOKEN`.

## Non-goals

Publishing an image, signing, release manifests (R2, R3); instance updates (#280). Deploy
(`deploy-podman.sh`, the `deploy` job) is unchanged.

## Capabilities

### New Capabilities
- `release-pipeline`: release versioning and tagging.

### Modified Capabilities
None.

## Impact

`scripts/`, `.gitlab-ci.yml`, `zebra-agent-web` version endpoint fallback and footer template,
`README-CICD.md`. No data model changes.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | A release tag can only be cut from a green master pipeline at the current master head | `release:tag` rules (manual, master push, last stage); script refuses other branches/sources, a moved master and an existing tag (`test_release_tag.py`) |
| O2 | The running version is visible in the API and UI | `version` in `/api/version/` on prod after deploy (`0.0.0+g<sha>` until the first tag); footer shows `vX.Y.Z` once tagged (`TestGenVersion`) |
| O3 | Release notes list the issues closed since the previous tag, security first, open issues dropped | `test_release_tag.py` notes tests; `--dry-run` output on master |
| O4 | Prod deploy is unchanged and the master pipeline stays green | `deploy` job and `deploy-podman.sh` untouched; master pipeline green with `release:tag` waiting as manual |
