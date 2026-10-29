## Why

Zebra can hand a build to Claude Code (#98), but only as a credential-free patch that a human
publishes as a draft MR. Nothing in it follows the development process, and every later step
(CI, merge, deploy check, outcome review) needs a host Claude session. Slice A of #251 gives the
host builder **delivery stages**, so a later Zebra workflow (slice B) can take its own repo
through the CLAUDE.md process with one human review. Part of #251.

## What Changes

- Build jobs gain `stage`: `patch` (default, unchanged), `propose`, `ship`, `review`, `merge`,
  plus `branch`, `issue`, and for `merge` an `approval {ship_job_id, head_sha}`.
- Each stage's sandbox gets a stage preamble (which CLAUDE.md steps to do, where to stop) and only
  its credentials, by name: a Developer GitLab token for `propose`/`ship`/`review`, GitHub for
  `ship`/`merge`, and the Maintainer GitLab token only for `merge`.
- `merge` starts only if the approved head is the one the builder recorded for that ship job and
  the branch is still there; otherwise it is rejected before anything is cloned.
- After a stage, the builder records from the remote, not the sandbox: branch head, changed and
  sensitive files, pipeline status, and for `merge` that the new master is a merge of the approved
  commit. A credential found in a pushed diff fails the stage and is audited.
- Sandbox image adds pinned, checksum-verified `glab`, `gh` and `openspec`.
- `deploy-podman.sh` writes `ZEBRA_BUILDER_GITLAB_TOKEN`, `_GITLAB_MERGE_TOKEN`, `_GITHUB_TOKEN`
  into `builder.env`; `--probe --stage <s>` checks each stage's credentials authenticate.
- `claude_code_build` takes `stage`, `branch`, `issue`, and reads a merge approval from the ship
  job's record and result.

## Capabilities

### New Capabilities
<!-- None -->

### Modified Capabilities
- `claude-code-builder`: delivery stages with per-stage credentials and host-checked results.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | Each stage's sandbox gets exactly its credentials and no other stage's, by name, never in argv | Unit tests per stage assert the env names/values and that the merge token is absent outside `merge`; prod `--probe --stage` for all five stages passes with the expected GitLab/GitHub identities |
| O2 | A merge runs only for the head commit a human approved, and the approval is recorded | Tests: wrong head, branch moved after approval, other branch and failed ship are rejected before cloning; a `merge_approved` audit line names ship job, head, issue and process; the merge commit's parents must include the approved head |
| O3 | Stage results carry facts the builder checked on the host, and no credential leaves it | Tests: `head_sha` / `merge_sha` from `git ls-remote`, `changed_files` / `sensitive_files` from the compare API, `pipeline` for the commit; summary and `report.json` redacted; a credential in a pushed diff fails the stage (`secret_pushed`) |
| O4 | *Build Software* (patch builds) behaves exactly as before | The 57 existing builder tests pass unchanged, including the exact sandbox environment |

## Non-goals

- The *Improve Zebra* workflow, Zebra's recommendation and the PR review task (slice B), and
  the merge and outcome-review workflow steps (slice C).
- Sandbox egress filtering; GitHub branch protection.

## Impact

`scripts/zebra_builder.py`, `deploy/builder/*`, `scripts/deploy-podman.sh`,
`zebra_tasks/builder/`, tests, `specs/claude-code-builder-design.md`, `specs/zebra-as-is.md`,
`README-CICD.md`.
