# Release pipeline (#283)

Part of the Onboarding epic (#275); consumed by first boot (#279) and instance updates (#280).
Slices: **R1** versioning + tag job (shipped), **R2** signed arm64 image in a public registry
(not started: needs registry credentials), **R3** signed release manifest and channels.

## 1. Goal & scope

Cut semver releases from green master and describe each one in a form an instance can trust.
arm64 only (2026-11-09 decision). Prod's host deploy (`deploy` job, `scripts/deploy-podman.sh`)
is unchanged: every release job is additive, and tag pipelines never deploy.

## 2. Data model

No tables. `version.json` gains `version` (from the newest `vX.Y.Z` tag: `0.3.0`,
`0.3.0+4.gabc1234` after it, `0.0.0+g<hash>` before the first release).

## 3. Interfaces

- `GET /api/version/`: `version` key (fallback `unknown`); footer shows `vX.Y.Z[+N]` once tagged.
- `scripts/release_tag.py [--ref SHA] [--bump major|minor|patch] [--version X.Y.Z]
  [--notes-file F] [--dry-run] [--no-fetch]`: next version, notes, GitLab release + tag.
- CI stage `release`, job `release:tag` (manual, master push only, artifact `release-notes.md`).

## 4. Control flow

Master push → lint → test → e2e → deploy → smoke → (owner presses) `release:tag`:
refuse unless master push pipeline, `ref` is still the master head, tag free, token set →
fetch tags (unshallow) → previous tag → next version → issues closed by commits in
`previous..ref` (`Closes`/`Fixes`/`Resolves #N`, looked up, open ones dropped, `security` first)
→ `POST /projects/:id/releases` (creates the tag at `ref`) → the tag pipeline runs
lint/test/e2e (deploy and smoke rules exclude tags).

`gen_version.py` reads the tag with `describe`; in a shallow CI clone without tags it fetches
tags with `--unshallow` once (best effort), so the `deploy` job needs no change.

## 5. Configuration

| Variable | Where | Purpose |
|---|---|---|
| `RELEASE_GITLAB_TOKEN` | CI, masked + protected | Owner PAT (`api`): read issues, create tags and releases. `CI_JOB_TOKEN` cannot; project tokens need a paid plan |
| `RELEASE_BUMP` / `RELEASE_VERSION` | set when running `release:tag` | Bump part (default `minor`) or exact version |

## 6. Open questions / risks

- First release notes list every issue closed in the whole history.
- Prod shows the new tag only from the next master deploy (the tagged commit was built before
  the tag existed): `0.3.0` appears as `0.3.0+1.g…` on the following deploy.
- Tag pipelines re-run e2e against the shared Always Free ADB (`resource_group: oracle-e2e`).
