## ADDED Requirements

### Requirement: Builds run in a secret-free sandbox
The host builder SHALL run each build's Claude Code session in a new podman container from the
sandbox image, as a non-root user mapped to the host user (`--userns=keep-id`), with memory and
pids limits, lowered CPU priority, `no-new-privileges`, all capabilities dropped, and only the job's workspace and
output directory mounted. The container environment SHALL contain the Claude Code OAuth token
and the job's own parameters, and no other credential.

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
SHALL ignore any output larger than its size cap. It SHALL redact the Claude token from all text
it returns, and SHALL refuse a patch that contains the token.

#### Scenario: Symlinked output is refused
- **WHEN** a sandbox leaves `changes.patch` as a symlink to a host file
- **THEN** the builder does not read the target and the result reports the output as missing

#### Scenario: Publish uses a fresh clone
- **WHEN** an approved build is published
- **THEN** the builder applies the patch to a new clone with hooks disabled and pushes from that
  clone, never from the sandbox workspace

### Requirement: Capability budgets are enforced and logged
Each build job SHALL declare a repo, `max_turns` and `minutes`. The builder SHALL reject without
cloning any job whose repo is not on `ZEBRA_BUILDER_REPOS` or whose limits exceed the server
ceilings. It SHALL kill a sandbox that runs past its minutes, and SHALL report a run that hits
`max_turns` as over budget. Every rejection and overrun SHALL be appended to the builder audit log
and returned in the result's `violations`, and `claude_code_build` results SHALL be recorded in
the process property `__builder_violations__` by the builder watcher.

#### Scenario: Repo not on the allowlist
- **WHEN** a job names a repo not on the allowlist
- **THEN** its result state is `rejected`, no container is started, and the audit log gains a
  line naming the repo

#### Scenario: Minutes exceeded
- **WHEN** a sandbox is still running after the job's minutes
- **THEN** the builder kills it and the result state is `over_budget` with a `minutes` violation

#### Scenario: Max turns reached
- **WHEN** Claude Code's JSON result has subtype `error_max_turns`
- **THEN** the result state is `over_budget` with a `max_turns` violation

### Requirement: Nothing is published without human approval
The *Build Software* workflow SHALL run `publish_build` only on the `approve` route of its human
review task, sending the `patch_sha256` of the result the reviewer saw. The builder SHALL
publish only a patch with that hash, at most once, and SHALL push only to a branch it names itself, `zebra-build/<job id
prefix>`, on an allowlisted repo, and SHALL open a draft merge request. It SHALL NOT push to any
other ref.

#### Scenario: Rejected review discards the build
- **WHEN** the reviewer chooses `reject`
- **THEN** no publish request is written and nothing is pushed

#### Scenario: Stale approval is refused
- **WHEN** the publish request's `patch_sha256` differs from the built patch
- **THEN** the builder pushes nothing and answers with an error

#### Scenario: Approved review opens a draft MR
- **WHEN** the reviewer chooses `approve`
- **THEN** the builder pushes `zebra-build/<prefix>` and the workflow output carries the draft MR URL

### Requirement: Builds park the goal and survive restarts
`claude_code_build` SHALL return after writing the job, and the workflow SHALL wait on an
`auto: false` task with `external: builder`, so the goal timeout does not apply and the daemon
moves on to other goals. The daemon's `BuilderWatcher` SHALL complete that task with the job
result and route by its state, and SHALL write a cancel request for a live job whose process is
FAILED or COMPLETE. External-wait tasks SHALL NOT be listed as human tasks. A restarted builder
SHALL resume supervising any running sandbox that still exists and fail jobs whose sandbox is gone.

#### Scenario: Result completes the wait
- **WHEN** a job's `result.json` exists and its process waits on the `external: builder` task
- **THEN** the watcher completes the task with the result as output and `next_route` set to the
  result's state

#### Scenario: Goal ended early
- **WHEN** a job is still running and its process is FAILED
- **THEN** the watcher writes `cancel` and the builder kills the sandbox

#### Scenario: Builder restarts mid-build
- **WHEN** the builder starts and a job is `running` with its container still present
- **THEN** it resumes waiting on that container instead of failing the job
