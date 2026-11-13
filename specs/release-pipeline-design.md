# Release pipeline (#283)

Part of the Onboarding epic (#275); consumed by first boot (#279) and instance updates (#280).
Slices: **R1** versioning + tag job (shipped), **R2** signed arm64 image in a public registry
(not started: needs registry credentials), **R3** signed release manifest and channels (tooling
shipped; CI jobs dormant until R2 and the bucket and key exist).

## 1. Goal & scope

Cut semver releases from green master and describe each one in a form an instance can trust.
arm64 only (2026-11-09 decision). Prod's host deploy (`deploy` job, `scripts/deploy-podman.sh`)
is unchanged: every release job is additive, and tag pipelines never deploy.

## 2. Data model

No tables. `version.json` gains `version` (from the newest `vX.Y.Z` tag: `0.3.0`,
`0.3.0+4.gabc1234` after it, `0.0.0+g<hash>` before the first release).

**Release manifest, schema v1** (`zebra_agent/release.py`, strict: unknown keys refused):

| Key | Rule |
|---|---|
| `schema` | `1` |
| `version`, `min_from` | `X.Y.Z`; `min_from` ≤ `version` (oldest version that may update straight to it; default `0.0.0`) |
| `channel` | `stable` / `next` / `test` |
| `image`, `digest` | `registry/repo@sha256:<64 hex>` (never a tag); `digest` equals the image's |
| `platforms` | `os/arch` list containing `linux/arm64` |
| `breaking` | bool; must be true when `migrations.contract` is non-empty |
| `migrations` | `{expand: [...], contract: [...]}` as `app.0001_name` |
| `notes_url`, `notes_md` | https URL or empty; Markdown (the GitLab release description) |
| `security`, `unsupported_below` | bool (auto when the notes have a Security section); `X.Y.Z` ≤ `version` or null |
| `published_at` | UTC ISO 8601 ending in `Z` |

**Bucket layout** (public Object Storage bucket, plan: `zebra-releases`):
`releases/vX.Y.Z.json(.sig)`, `channels/next.json(.sig)`, `channels/stable.json(.sig)`. A
channel file is the release manifest with `channel` set. Files are written as sorted-key JSON
(`dump_manifest`) and signed byte for byte.

## 3. Interfaces

- `GET /api/version/`: `version` key (fallback `unknown`); footer shows `vX.Y.Z[+N]` once tagged.
- `scripts/release_tag.py [--ref SHA] [--bump major|minor|patch] [--version X.Y.Z]
  [--notes-file F] [--dry-run] [--no-fetch]`: next version, notes, GitLab release + tag.
- `zebra_agent.release`: `validate_manifest` / `manifest_errors`, `verify_blob`,
  `load_verified` (signature first, then schema), `sign_blob` (tests/offline), `dump_manifest`.
- `scripts/release_manifest.py [--dir release-dist] build|sign|verify|promote|publish|fetch`
  (see its docstring). Signing: `cosign sign-blob --tlog-upload=false` with the project key, or
  in-process for a plain PEM EC key. Verifying: in-process (same format as cosign: base64 DER
  ECDSA P-256 over SHA-256), `--cosign` also runs `cosign verify-blob --insecure-ignore-tlog`.
- CI stage `release`: `release:tag` (manual, master push only, artifact `release-notes.md`);
  `release:manifest` (auto) and `release:promote-stable` (manual) on `vX.Y.Z` tag pipelines
  only, and only when `RELEASE_BUCKET` and `COSIGN_PRIVATE_KEY` are set.

## 4. Control flow

Master push → lint → test → e2e → deploy → smoke → (owner presses) `release:tag`:
refuse unless master push pipeline, `ref` is still the master head, tag free, token set →
fetch tags (unshallow) → previous tag → next version → issues closed by commits in
`previous..ref` (`Closes`/`Fixes`/`Resolves #N`, looked up, open ones dropped, `security` first)
→ `POST /projects/:id/releases` (creates the tag at `ref`) → the tag pipeline runs
lint/test/e2e (deploy and smoke rules exclude tags).

Tag pipeline (once configured) → R2 image job (sets `RELEASE_IMAGE` by dotenv) →
`release:manifest`: build (`expand` = migration files added since the previous tag; notes from
the GitLab release) → write `releases/vX.Y.Z.json` + `channels/next.json` → sign → verify →
upload (file, then `.sig`). `release:promote-stable` (manual): fetch the release manifest and
its signature → verify → copy to `channels/stable.json` → sign → verify → upload only that pair.
A tampered byte, a missing or foreign signature, or a schema error fails verification; an
unsigned file is never published.

`gen_version.py` reads the tag with `describe`; in a shallow CI clone without tags it fetches
tags with `--unshallow` once (best effort), so the `deploy` job needs no change.

## 5. Configuration

| Variable | Where | Purpose |
|---|---|---|
| `RELEASE_GITLAB_TOKEN` | CI, masked + protected | Owner PAT (`api`): read issues, create tags and releases, read release notes. `CI_JOB_TOKEN` cannot; project tokens need a paid plan |
| `RELEASE_BUMP` / `RELEASE_VERSION` | set when running `release:tag` | Bump part (default `minor`) or exact version |
| `COSIGN_PRIVATE_KEY` (file) / `COSIGN_PASSWORD` | CI, protected (+ masked password) | Project signing key from `cosign generate-key-pair`; its public half is committed as `deploy/release/cosign.pub` (`RELEASE_PUBKEY`) |
| `RELEASE_BUCKET` / `RELEASE_BUCKET_NAMESPACE` | CI | Public release bucket (uploads use the host's `oci` CLI profile) |
| `RELEASE_UNSUPPORTED_BELOW` | set when running a tag pipeline | `unsupported_below` for a security release |

Protected variables reach tag pipelines only for protected tags: protect `v*` (Maintainers)
before setting the key.

## 6. Open questions / risks

- First release notes list every issue closed in the whole history.
- Prod shows the new tag only from the next master deploy (the tagged commit was built before
  the tag existed): `0.3.0` appears as `0.3.0+1.g…` on the following deploy.
- Tag pipelines re-run e2e against the shared Always Free ADB (`resource_group: oracle-e2e`).
- Not yet done: the key pair, `deploy/release/cosign.pub`, the bucket, `v*` tag protection, cosign
  on the host (R2 pins it in `bootstrap-host.sh`), retention of 5 releases, publishing the #279
  stack zip. The #279 Always Free plan scan (`iac` job, `scripts/oci_plan_scan.py`) has no rules,
  so it already runs on every release tag pipeline. In-process verification matches cosign's documented `sign-blob`
  format but was not cross-checked against a real cosign binary (not installed on the host).
- Classifying contracting migrations automatically is U1 (`check_migrations.py`); until then
  `--contract` is manual.
- Key rotation: a new key needs a manifest-signed key list (later slice); today the public key
  is pinned in the image/stack.
