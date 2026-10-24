# repo-ops-actions Specification

## Purpose
Git task actions (`git_clone`, `git_status`, `git_diff`, `git_branch`, `git_commit`, `git_pull`, `git_push`) that let a workflow wrap an agent step in a repository, sandboxed to `ZEBRA_GIT_WORKSPACE`, with host-scoped credentials and an irreversible, protected-branch-guarded push (#64).

## Requirements

### Requirement: Workspace sandbox
Every Git action SHALL operate only on paths inside the workspace directory (`workspace` property, else `ZEBRA_GIT_WORKSPACE`). A path that resolves outside it SHALL fail the task without running Git.

#### Scenario: Path inside workspace
- **WHEN** `repo_path` resolves inside the workspace
- **THEN** the action runs Git in that directory

#### Scenario: Path escapes workspace
- **WHEN** `repo_path` or `dest` resolves outside the workspace (absolute path or `..`)
- **THEN** the task fails with a security error and no Git command runs

#### Scenario: No workspace configured
- **WHEN** neither the `workspace` property nor `ZEBRA_GIT_WORKSPACE` is set
- **THEN** the task fails with a configuration error

### Requirement: Clone into the workspace
`git_clone` SHALL clone `url` into `dest`, defaulting to `<workspace>/<process id>/<repo name>`, optionally checking out `branch` and limiting history with `depth`. It SHALL output the absolute `path`, `branch` and `head` commit.

#### Scenario: Clone succeeds
- **WHEN** the remote is allowed and reachable
- **THEN** the repository is cloned to the destination and the output gives its path, branch and head

#### Scenario: Remote refused
- **WHEN** the URL starts with `-`, uses `ext::`, `file://` or `http://`, or is a local path outside the workspace
- **THEN** the task fails and nothing is cloned

### Requirement: Inspect changes
`git_status` SHALL report the current branch, whether the tree is clean and the changed files. `git_diff` SHALL return the diff of the working tree (or `staged`, or against `base`), truncated to `max_chars` with a `truncated` flag.

#### Scenario: Changed file reported
- **WHEN** a file in the repo was modified by an earlier step
- **THEN** `git_status` lists it with `clean: false` and `git_diff` contains its change

#### Scenario: Large diff truncated
- **WHEN** the diff is longer than `max_chars`
- **THEN** the output diff is cut to `max_chars` and `truncated` is true

### Requirement: Branch, commit and pull locally
`git_branch` SHALL check out `name`, creating it from `start_point` when `create` is true. `git_commit` SHALL stage `paths` (default all changes) and commit with `message` under the configured author; when nothing changed it SHALL succeed with `committed: false`. `git_pull` SHALL pull fast-forward only.

#### Scenario: Commit made
- **WHEN** the tree has changes and a message is given
- **THEN** a commit is created and the output gives its sha and `committed: true`

#### Scenario: Nothing to commit
- **WHEN** the tree is clean
- **THEN** the task succeeds with `committed: false`

#### Scenario: Option-like ref refused
- **WHEN** a branch, ref or path value starts with `-`
- **THEN** the task fails and no Git command runs

### Requirement: Guarded push
`git_push` SHALL push the current (or named) branch to `remote` and declare `reversibility_hint = "always_irreversible"`. It SHALL refuse `main` and `master` unless `allow_protected` is true, and SHALL offer no force push.

#### Scenario: Feature branch pushed
- **WHEN** the branch is not protected and the remote accepts it
- **THEN** the remote has the branch at the local head and the task succeeds

#### Scenario: Protected branch refused
- **WHEN** the branch is `main` or `master` and `allow_protected` is not true
- **THEN** the task fails and nothing is pushed

### Requirement: Credentials stay scoped
`token_env` SHALL name a `ZEBRA_GIT_TOKEN*` variable. Its token SHALL be supplied through Git config environment variables as an auth header scoped to the hosts in `ZEBRA_GIT_TOKEN_HOSTS` (default `gitlab.com`), never on the command line, and SHALL NOT appear in any task output or error.

#### Scenario: Header scoped to configured hosts
- **WHEN** a token is set and `ZEBRA_GIT_TOKEN_HOSTS` is `gitlab.com`
- **THEN** the Git environment carries the header only under `http.https://gitlab.com/.extraHeader` and the token is not in argv

#### Scenario: Other secrets refused
- **WHEN** `token_env` names a variable that does not start with `ZEBRA_GIT_TOKEN`
- **THEN** the task fails and no Git command runs

#### Scenario: Error output redacted
- **WHEN** Git fails and its stderr contains the token
- **THEN** the task error shows `***` in place of the token

### Requirement: Repository config cannot run commands
Before acting on an existing repository the actions SHALL check its local config against an allowlist of plain clone/branch keys and check every remote URL as for cloning. Push and pull SHALL accept only a configured remote name, never a URL.

#### Scenario: Edited config refused
- **WHEN** an earlier step added `core.fsmonitor`, a `filter.*` driver or `url.*.insteadOf` to `.git/config`
- **THEN** the next Git action fails without running the configured command

#### Scenario: Raw URL as remote refused
- **WHEN** `git_push` is given a URL instead of a configured remote name
- **THEN** the task fails and nothing is pushed

### Requirement: Reversibility metadata
`git_clone`, `git_status`, `git_diff`, `git_branch`, `git_commit` and `git_pull` SHALL declare `always_reversible`; `git_push` SHALL declare `always_irreversible`.

#### Scenario: Metadata
- **WHEN** the action metadata is inspected
- **THEN** each action reports the hint above
