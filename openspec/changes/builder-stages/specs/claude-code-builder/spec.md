## MODIFIED Requirements

### Requirement: Builds run in a secret-free sandbox
The host builder SHALL run each build's Claude Code session in a new podman container from the
sandbox image, as a non-root user mapped to the host user (`--userns=keep-id`), with memory and
pids limits, lowered CPU priority, `no-new-privileges`, all capabilities dropped, and only the job's workspace and
output directory mounted. The container environment SHALL contain the Claude Code OAuth token,
the job's own parameters, and only the credentials its delivery stage is given, and no other
credential. Credentials SHALL be passed by name only, never as command-line values.

#### Scenario: Escape probe passes
- **WHEN** `zebra_builder.py --probe` runs the sandbox command with the probe entrypoint
- **THEN** the sandbox runs as a non-root uid with no effective capabilities and `NoNewPrivs`,
  sees only `/workspace` and `/out` from the host, no secret files and no container socket, and
  cannot write system directories

#### Scenario: Sandbox command is constrained
- **WHEN** the builder starts a build
- **THEN** the `podman run` arguments include `--userns=keep-id`, `--memory`,
  `--pids-limit`, `--cap-drop=all`, `--security-opt=no-new-privileges`, exactly two `-v` mounts
  (workspace and output), and pass `CLAUDE_CODE_OAUTH_TOKEN` by name only

### Requirement: The host treats sandbox output as untrusted data
The builder SHALL NOT run git or any other program inside a workspace after a sandbox has run in
it. It SHALL read sandbox outputs only as regular files opened without following symlinks, and
SHALL ignore any output larger than its size cap. It SHALL redact every credential it holds from
all text it returns, and SHALL refuse a patch that contains one.

#### Scenario: Symlinked output is refused
- **WHEN** a sandbox leaves `changes.patch` as a symlink to a host file
- **THEN** the builder does not read the target and the result reports the output as missing

#### Scenario: Publish uses a fresh clone
- **WHEN** an approved build is published
- **THEN** the builder applies the patch to a new clone with hooks disabled and pushes from that
  clone, never from the sandbox workspace

## ADDED Requirements

### Requirement: Delivery stages get only their own credentials
A build job MAY name a delivery `stage` (`propose`, `ship`, `review`, `merge`) with a feature
`branch` and an `issue`; a job without one is a `patch` build and SHALL run exactly as before.
Stages SHALL run only on the builder's own repo (`ZEBRA_BUILDER_SELF_REPO`). The builder SHALL
give `propose`, `ship` and `review` the Developer GitLab token, `ship` and `merge` the GitHub
token, and only `merge` the Maintainer GitLab token. A stage whose credential is not configured
SHALL fail before cloning. Each stage's prompt SHALL say which CLAUDE.md steps to do and where to
stop.

#### Scenario: Ship gets its two credentials by name
- **WHEN** a `ship` job starts
- **THEN** the sandbox environment has `GITLAB_TOKEN` (Developer) and `GH_TOKEN`, passed by name,
  and no Maintainer token

#### Scenario: Stage credentials authenticate
- **WHEN** `zebra_builder.py --probe --stage ship` runs on the host
- **THEN** the probe reports the GitLab and GitHub login names and no unexpected variables

#### Scenario: Patch build environment unchanged
- **WHEN** a job without `stage` starts
- **THEN** no stage variable or stage credential is in the sandbox environment

### Requirement: A merge runs only for the approved head
A `merge` job SHALL carry `approval {ship_job_id, head_sha}`. The builder SHALL start it only if
that job is a `ship` for the same repo, branch and issue, its result is `done` with that
`head_sha`, and the remote branch is still at that commit. Otherwise the job SHALL be rejected
before cloning and audited.

#### Scenario: Branch moved after approval
- **WHEN** the branch head on the remote differs from the approved `head_sha`
- **THEN** the merge is `rejected`, nothing is cloned and the audit log records it

### Requirement: Stage results are checked on the host
After a stage the builder SHALL record, from the remote rather than the sandbox, the branch head
(`propose`, `ship`), changed and sensitive files, and the latest pipeline for that commit. A stage
that pushed nothing SHALL fail. A pushed diff containing a builder credential SHALL fail the
stage and be audited. A `merge` SHALL fail unless the base branch moved to a commit whose parents
include the approved head. A `review` SHALL fail without a `verdicts` list. Stage jobs SHALL NOT
be published.

#### Scenario: Ship result from the remote
- **WHEN** a ship sandbox finishes after pushing its branch
- **THEN** the result has `head_sha` from `git ls-remote`, `changed_files` and `sensitive_files`
  from the compare API, and `pipeline` for that commit

#### Scenario: Merge of the wrong commit
- **WHEN** master moves to a commit whose parents do not include the approved head
- **THEN** the merge result is `failed` and the audit log records `merge_mismatch`
