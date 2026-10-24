## ADDED Requirements

### Requirement: Local remotes are opt-in
A remote that is a local path SHALL be refused unless `ZEBRA_GIT_ALLOW_LOCAL_REMOTES` is `1`, both when cloning and when a repository's config names it. With the opt-in, the path SHALL still resolve inside the workspace.

#### Scenario: Local clone source refused
- **WHEN** `git_clone` is given a local path and the opt-in is not set
- **THEN** the task fails and Git never reads that repository

#### Scenario: Config pointing at a local path refused
- **WHEN** a repository's `remote.origin.url` is a local path and the opt-in is not set
- **THEN** the next Git action on that repository fails and nothing is pushed

### Requirement: Minimal Git environment
Git SHALL run with only an allowlist of the process environment (path, home, locale, time zone, temp dir, CA and proxy variables) plus its own settings, and with no askpass helper.

#### Scenario: Other secrets withheld
- **WHEN** API keys, database credentials or other tokens are set in Zebra's environment
- **THEN** none of them is in the environment Git runs with

#### Scenario: Auth challenge fails fast
- **WHEN** a server asks for credentials
- **THEN** Git fails without prompting or sending a placeholder

### Requirement: Repository and branch name checks
The actions SHALL refuse a repository whose `.git` is a symlink. `git_push` SHALL refuse a branch name that `git check-ref-format --branch` rejects, and SHALL treat `main` and `master` as protected regardless of case.

#### Scenario: Symlinked .git refused
- **WHEN** `repo_path` has a `.git` symlink
- **THEN** the task fails

#### Scenario: Protected branch in other case refused
- **WHEN** `git_push` is asked to push `MAIN` or `Master` without `allow_protected`
- **THEN** the task fails and nothing is pushed
