## Context

#283 needs semver tags cut from master after a green deploy. CI runs on one shell runner on the
prod host; checkouts are shallow (depth 20) and do not fetch tags. The GitLab project is private.

## Decisions

- **Version from `describe`** against `v[0-9]*.[0-9]*.[0-9]*` tags, written into
  `version.json` at image build (no VCS calls at runtime, as before). Distance after a tag is
  semver build metadata (`0.3.0+4.gabc1234`), so it never sorts below the tag. Before any tag:
  `0.0.0+g<hash>`; the footer hides that.
- **Shallow clones**: when `describe` finds nothing in a shallow repo, `gen_version.py` fetches
  tags with `--unshallow` once (120 s timeout, failures only warn). This keeps the `deploy` job
  untouched. `release_tag.py` always fetches tags (and unshallows) before reading.
- **Tag via the GitLab Releases API**: `POST /projects/:id/releases` with `ref` creates tag and
  release in one call, with the notes as the description. A personal access token
  (`RELEASE_GITLAB_TOKEN`, masked + protected) is needed: `CI_JOB_TOKEN` cannot create tags or
  read issues, and project access tokens need a paid plan.
- **Green-master gate** is structural (manual job, master push rule, last stage after `smoke`, so
  GitLab skips it when an earlier stage failed) and checked again by the script (branch, source,
  `ref` == current master head so a retried stale pipeline cannot tag old code, tag not taken).
- **Notes from commits, filtered by issue state**: issue numbers come from closing keywords in
  commit messages in `previous..ref`; each is looked up and kept only if closed. The first
  release lists the whole history.
- **First version** is `0.1.0` (matches the packages); bump default `minor` while pre-1.0.

## Interfaces

- `version.json` / `GET /api/version/`: new `version` key (fallback `"unknown"`).
- CLI: `scripts/release_tag.py [--ref SHA] [--bump major|minor|patch] [--version X.Y.Z]
  [--notes-file F] [--dry-run] [--no-fetch]`; exit 1 with a reason when refused.
- CI: stage `release`, job `release:tag` (artifact `release-notes.md`).

No data model, store or setting changes. `specs/zebra-as-is.md`: CI/CD section (release stage).

## Risks

- The tag pipeline runs lint/unit/e2e again (deploy/smoke rules exclude tags): extra e2e load.
- `RELEASE_GITLAB_TOKEN` is not set yet; the job fails with a clear message until the owner adds
  it. That is harmless: it is manual and allowed to fail.
