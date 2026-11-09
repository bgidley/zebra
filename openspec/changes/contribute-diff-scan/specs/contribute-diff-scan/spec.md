## ADDED Requirements

### Requirement: Added content only
The `contribute_diff_scan` action SHALL scan the added lines of a unified diff, every touched file
path, the commit messages, the PR title and body and the author name, and SHALL NOT treat context
or removed lines as content. Any diff line outside a hunk that is not a git header SHALL be
scanned as text.

#### Scenario: Secret on a removed line
- **WHEN** a diff removes a line holding a GitHub token and adds nothing sensitive
- **THEN** the scan routes `clean` (given a clean LLM verdict)

#### Scenario: Secret in a commit message
- **WHEN** a commit message holds a GitHub token
- **THEN** the scan routes `rejected` with a `secret` finding located at that commit message

### Requirement: Rules
The scan SHALL reject on the Commons personal-data rules, the Commons confidentiality rules
(except the generic URL and `key: value` credential rules), the configured confidential patterns,
secret rules (known token formats, armored `-----BEGIN` blocks, OCI user / tenancy / key ocids,
AWS keys, JWTs, quoted secret literals, high-entropy strings of 32+ characters) and blocked files
(`.env*`, `*.pem`, `*.key`, `site.env`, key stores, credential directories, binaries). Findings
SHALL be masked and located. `SENSITIVE_PATHS` SHALL be listed in `sensitive_files` without
rejecting.

#### Scenario: Blocked file
- **WHEN** a diff adds `.env`
- **THEN** the scan routes `rejected` with a `blocked_file` finding for `.env`

#### Scenario: Sensitive path
- **WHEN** a clean diff changes `.gitlab-ci.yml`
- **THEN** the scan routes `clean` and lists `.gitlab-ci.yml` in `sensitive_files`

### Requirement: Fail closed
The scan SHALL route `clean` only when the diff parses, no rule fires and the one low-tier LLM call
answers `personal_data: false` with no findings. An empty or malformed diff, more than `max_chars`
of text, no LLM, a failed call or a reply without a boolean verdict SHALL route `rejected` with
`failed_closed: true`.

#### Scenario: Empty LLM reply
- **WHEN** the LLM returns an empty reply for a diff the rules pass
- **THEN** the scan routes `rejected` with `failed_closed: true`

#### Scenario: Clean diff
- **WHEN** a real repo diff with no secrets or personal data is scanned and the LLM answers
  `personal_data: false`
- **THEN** the scan routes `clean`

### Requirement: Output
The result SHALL hold `verdict` (`clean` | `rejected`), `clean`, `findings`, `failed_closed`,
`reason`, `files`, `sensitive_files`, `added_lines`, `diff_sha256` and `author_email`: the GitHub
noreply address (`<id>+<login>@users.noreply.github.com`, or `<login>@…` without an id) when a
valid login is given, else null. The action SHALL store it under `output_key` (default
`diff_scan`) and write nothing else.

#### Scenario: Author email rewritten
- **WHEN** the login `octo` with id `42` is given
- **THEN** `author_email` is `42+octo@users.noreply.github.com`
