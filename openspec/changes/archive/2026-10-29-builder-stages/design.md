## Context

The host builder (#98, `scripts/zebra_builder.py`) is Zebra's capability boundary for code: it
accepts one fixed job schema, runs Claude Code in a podman sandbox, and treats everything the
sandbox writes as hostile. #251 wants Zebra to deliver its own changes through the CLAUDE.md
process. The user chose to run that process **inside the sandbox** (Claude Code already knows it)
with one human review of the GitHub PR. Slice A is the builder side; the workflow is slice B.

## Decisions

**Stages, not new job kinds.** `kind: build` stays; `stage` selects the preamble, credentials and
collection. A job without `stage` is a `patch` build and runs byte-for-byte as before (no new
environment variables), so *Build Software* is untouched.

**Credentials per stage, by name.** `STAGE_TOKENS` maps stage to config attributes; the values
go into the `podman run` environment as `GITLAB_TOKEN` / `GH_TOKEN` (what glab and gh read), and
only names go into argv. `sandbox-run.sh` adds git credential helpers that read the env at push
time, so no token is written to disk. GitLab protection does the rest: the Developer token
(`zebra.gidley`) cannot push the Maintainers-only master.

| Stage | GitLab | GitHub | Clone |
|---|---|---|---|
| propose | Developer | — | base, then `checkout -b branch` on the host before the sandbox runs (or the branch if it exists) |
| ship | Developer | yes | the branch (or base + new branch) |
| review | Developer | — | base |
| merge | Maintainer | yes | base |

**Approval binding.** A merge job carries `{ship_job_id, head_sha}`. Before cloning, the builder
checks the ship job is a `ship` for the same repo, branch and issue, its result is `done` with
that `head_sha` (recorded by the builder from `git ls-remote`, not by the sandbox), and the
remote branch is still at it. After the merge it checks master's new head has the approved commit
as a parent. This mirrors `patch_sha256` for publish: Zebra's workflow is trusted to write the
approval only on the human's `merge` route; the builder makes sure the approval matches what was
actually built and is still current.

**Facts from the host.** The sandbox's `report.json` is passed on (capped, redacted) as its own
account. The builder separately records `head_sha` / `merge_sha` (`git ls-remote`, host
credentials), `changed_files` / `sensitive_files` (GitLab compare API) and `pipeline`
(`{id, status, web_url}` for that commit), so slice B's recommendation does not depend on the
sandbox telling the truth. A pushed diff containing any builder credential fails the stage.

**Probe per stage.** `--probe --stage <s>` passes that stage's real credentials; the probe makes
read-only `glab api user` / `gh api user` calls and reports only the login names.

## Interface changes

- Job JSON: `stage`, `branch`, `issue`, `approval` (merge). Result JSON for stages: `stage`,
  `branch`, `issue`, `report`, `head_sha` / `merge_sha`, `changed_files`, `sensitive_files`,
  `pipeline`. No patch fields.
- `claude_code_build`: inputs `stage`, `branch`, `issue`, `approval_job_key` (`ship_job`),
  `approval_result_key` (`ship_result`).
- `BuilderSpool.submit_build(..., stage, branch, issue, approval)`.
- Builder env: `ZEBRA_BUILDER_GITLAB_TOKEN`, `_GITLAB_MERGE_TOKEN`, `_GITHUB_TOKEN`,
  `_SELF_REPO` (`gidley/zebra`), `_GITHUB_REPO` (`bgidley/zebra`). No data model change.

`specs/zebra-as-is.md`: the builder bullet; `specs/claude-code-builder-design.md`: stages section,
config table and risks.

## Risks

- The sandbox network is open and now holds push credentials. Developer-scoped GitLab token,
  protected master, merge only after approval, redaction and the pushed-secret check limit it.
- The GitHub token is the owner's and could push the mirror's master; GitHub is not the deploy
  source. It expires 2026-11-26.
- Branch pipelines started by a stage run on the prod host; `sensitive_files` goes to the
  reviewer.
- A compromised Zebra could write its own approval; the human gate lives in the workflow, as for
  publish today.
