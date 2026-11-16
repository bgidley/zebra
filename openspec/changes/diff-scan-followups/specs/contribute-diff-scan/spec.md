## MODIFIED Requirements

### Requirement: Rules
The scan SHALL reject on the Commons personal-data rules, the Commons confidentiality rules
(except the generic URL and `key: value` credential rules), the configured confidential patterns,
secret rules (known token formats, armored `-----BEGIN` blocks, OCI user / tenancy / key ocids,
AWS keys, JWTs, quoted secret literals, high-entropy strings of 32+ characters) and blocked files
(`.env*`, `*.pem`, `*.key`, `site.env`, key stores, credential directories, binaries). Added lines
of dependency lock files SHALL get the secret rules, the personal-data rules and the confidential
patterns too (with package URLs, hashes, `version = "..."` values and the `ip_address` kind left
out as false positives), but SHALL NOT get the host rule or reach the LLM. Findings SHALL be masked
and located. `SENSITIVE_PATHS` SHALL be listed in `sensitive_files` without rejecting.

#### Scenario: Blocked file
- **WHEN** a diff adds `.env`
- **THEN** the scan routes `rejected` with a `blocked_file` finding for `.env`

#### Scenario: Sensitive path
- **WHEN** a clean diff changes `.gitlab-ci.yml`
- **THEN** the scan routes `clean` and lists `.gitlab-ci.yml` in `sensitive_files`

#### Scenario: Email in a lock file
- **WHEN** a diff adds an email address to `uv.lock`
- **THEN** the scan routes `rejected` with an `email` finding located at that line

#### Scenario: Ordinary lock file
- **WHEN** a diff adds a real `uv.lock` (versions, package URLs, hashes)
- **THEN** the scan finds nothing in it

### Requirement: Fail closed
The scan SHALL route `clean` only when the diff parses, no rule fires and the one low-tier LLM call
answers `personal_data: false` with no findings. An empty or malformed diff, a diff longer than
`MAX_DIFF_CHARS` (2,000,000 characters, lock files included, checked before parsing), more than
`max_chars` of LLM text, no LLM, a failed call or a reply without a boolean verdict SHALL route
`rejected` with `failed_closed: true`. A file entry with no hunk, binary patch, mode, rename or copy
line SHALL be malformed; mode-only changes, empty new files, empty deletions and pure renames SHALL
still parse.

#### Scenario: Empty LLM reply
- **WHEN** the LLM returns an empty reply for a diff the rules pass
- **THEN** the scan routes `rejected` with `failed_closed: true`

#### Scenario: Clean diff
- **WHEN** a real repo diff with no secrets or personal data is scanned and the LLM answers
  `personal_data: false`
- **THEN** the scan routes `clean`

#### Scenario: Raw diff too large
- **WHEN** a diff of lock-file lines exceeds `MAX_DIFF_CHARS`
- **THEN** the scan routes `rejected` with `failed_closed: true` and the LLM is not called

#### Scenario: Header-only file entry
- **WHEN** a diff holds a file header line with only an `index` line and no hunk, mode or rename
- **THEN** the scan routes `rejected` with `failed_closed: true`

#### Scenario: Mode-only change
- **WHEN** a diff changes only a file's mode (`old mode` / `new mode`)
- **THEN** the scan routes `clean`

### Requirement: Output
The result SHALL hold `verdict` (`clean` | `rejected`), `clean`, `findings`, `failed_closed`,
`reason`, `files`, `sensitive_files`, `added_lines`, `diff_sha256` and `author_email`: the GitHub
noreply address (`<id>+<login>@users.noreply.github.com`, or `<login>@…` without an id) when a
valid login is given, else null. The action SHALL store it under `output_key` (default
`diff_scan`). Its only process-property writes SHALL be that key and the LLM client's cost
bookkeeping for its one call (`__total_tokens__`, `__total_cost__`, `__token_history__`); it SHALL
change nothing outside the run.

#### Scenario: Author email rewritten
- **WHEN** the login `octo` with id `42` is given
- **THEN** `author_email` is `42+octo@users.noreply.github.com`

#### Scenario: Properties written
- **WHEN** the action runs with `output_key` `scan`
- **THEN** the properties it wrote are within `scan`, `__total_tokens__`, `__total_cost__` and `__token_history__`
