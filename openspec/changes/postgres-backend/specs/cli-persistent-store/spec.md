## MODIFIED Requirements

### Requirement: CLI refuses to run against a non-Oracle backend by default
Because Django settings fall back to SQLite when no server database is configured, the
`zebra goal` and `zebra goals` commands SHALL check the active database backend after Django
initialisation. If the backend is neither Oracle nor PostgreSQL, the command SHALL print the
active backend and the environment variables that select a server database (Oracle or
`ZEBRA_DB_ENGINE=postgresql` with the `PG*` variables), then exit with a non-zero status code —
unless `--allow-sqlite` is explicitly passed.

#### Scenario: Missing Oracle credentials abort loudly
- **WHEN** `zebra goal "..."` is run with neither `ORACLE_DSN` nor `ZEBRA_DB_ENGINE=postgresql` set
- **THEN** the command prints that the SQLite fallback is active, names the variables, and exits non-zero without processing the goal

#### Scenario: PostgreSQL accepted
- **WHEN** `zebra goal "..."` is run with `ZEBRA_DB_ENGINE=postgresql`
- **THEN** the backend check passes without `--allow-sqlite`

#### Scenario: Explicit SQLite opt-in
- **WHEN** `zebra goal "..." --allow-sqlite` is run without server database credentials
- **THEN** the goal is processed against the SQLite database
