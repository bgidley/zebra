## ADDED Requirements

### Requirement: zebra CLI processes goals against persistent Oracle storage
The system SHALL provide a `zebra goal "<text>"` console command (entry point in
`zebra-agent-web`) that processes a goal using the same Oracle-backed stores
(`DjangoMemoryStore`, `DjangoMetricsStore`, `DjangoStore`) as the web application,
printing the result to stdout on completion.

#### Scenario: Goal runs and output printed
- **WHEN** `zebra goal "Write a haiku about clouds"` is run with valid Oracle credentials
- **THEN** the goal is processed, output is printed to stdout, and a `WorkflowRunModel` record is created in Oracle

#### Scenario: Goal appears in web dashboard after CLI run
- **WHEN** a goal is submitted via the CLI
- **THEN** the run is retrievable through the same metrics store the web dashboard's activity view reads

### Requirement: CLI refuses to run against a non-Oracle backend by default
Because Django settings silently fall back to SQLite when `ORACLE_*` variables are unset,
the `zebra goal` and `zebra goals` commands SHALL check the active database backend after
Django initialisation. If the backend is not Oracle, the command SHALL print the active
backend and the required environment variables, then exit with a non-zero status code —
unless `--allow-sqlite` is explicitly passed.

#### Scenario: Missing Oracle credentials abort loudly
- **WHEN** `zebra goal "..."` is run without `ORACLE_DSN` set
- **THEN** the command prints that the SQLite fallback is active, names the missing variables, and exits non-zero without processing the goal

#### Scenario: Explicit SQLite opt-in
- **WHEN** `zebra goal "..." --allow-sqlite` is run without Oracle credentials
- **THEN** the goal is processed against the SQLite database

### Requirement: CLI supports model selection
The `zebra goal` command SHALL accept a `--model` flag accepting the same aliases as the
web (`haiku`, `sonnet`, `opus`, `kimi`), defaulting to `haiku`.

#### Scenario: Non-default model used
- **WHEN** `zebra goal "..." --model kimi` is run
- **THEN** the Kimi LLM provider is used for the goal

### Requirement: CLI queue mode shares the web's queueing code path
The `zebra goal --queue` command SHALL create a CREATED process for daemon execution via
the same `queue_goal()` helper used by the web's queue endpoint, then exit immediately
printing the process ID. Queued goals from the CLI and the web SHALL be indistinguishable
in stored properties (aside from user identity fields).

#### Scenario: Queued goal picked up by daemon
- **WHEN** `zebra goal "..." --queue` is run
- **THEN** a CREATED process is written to Oracle, its ID is printed, and the CLI exits; the running daemon picks it up on its next poll

#### Scenario: Web queue endpoint behaviour preserved
- **WHEN** a goal is queued through the web form after the refactor
- **THEN** the created process has the same properties as before the refactor

### Requirement: CLI goals subcommand lists recent runs
The `zebra goals` command SHALL list recent workflow runs from Oracle, showing run ID,
workflow name, goal text (truncated), success status, and start timestamp, newest first.

#### Scenario: Goals listed
- **WHEN** `zebra goals` is run with valid Oracle credentials
- **THEN** recent runs are printed, newest first, up to the default limit of 10

#### Scenario: Custom limit
- **WHEN** `zebra goals --limit 25` is run
- **THEN** up to 25 recent runs are listed
