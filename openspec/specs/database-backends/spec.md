# database-backends Specification

## Purpose
TBD - created by archiving change postgres-backend. Update Purpose after archive.

## Requirements

### Requirement: Database backend selection
The web application SHALL choose its database from `ZEBRA_DB_ENGINE`: `oracle`, `postgresql`
(alias `postgres`) or `sqlite`, case-insensitive. When `ZEBRA_DB_ENGINE` is unset it SHALL use
Oracle if `ORACLE_DSN` is set and SQLite otherwise. An unsupported value SHALL fail start-up with
`ImproperlyConfigured`.

#### Scenario: Existing Oracle deployment unchanged
- **WHEN** `ORACLE_DSN`, `ORACLE_USERNAME` and `ORACLE_PASSWORD` are set and `ZEBRA_DB_ENGINE` is unset
- **THEN** the default database is the Zebra Oracle backend with that DSN, user and password

#### Scenario: Explicit engine wins
- **WHEN** `ZEBRA_DB_ENGINE=postgresql` and `ORACLE_DSN` are both set
- **THEN** the default database is PostgreSQL

#### Scenario: Unknown engine
- **WHEN** `ZEBRA_DB_ENGINE=mysql`
- **THEN** settings raise `ImproperlyConfigured` naming the value, instead of falling back to SQLite

### Requirement: PostgreSQL server backend
With `ZEBRA_DB_ENGINE=postgresql` the application SHALL connect to PostgreSQL using `PGHOST`,
`PGPORT`, `PGDATABASE`, `PGUSER` and `PGPASSWORD` (defaults `localhost`, `5432`, `zebra`,
`zebra`, empty). All migrations SHALL apply to an empty PostgreSQL 16 database, and the web unit
suite SHALL pass when run with `ZEBRA_TEST_DB_ENGINE=postgresql`. Vector memory search SHALL fall
back to keyword ranking on PostgreSQL until pgvector support is added.

#### Scenario: Fresh database
- **WHEN** `manage.py migrate` runs against an empty PostgreSQL 16 database
- **THEN** every migration applies without error

#### Scenario: Unit suite on PostgreSQL
- **WHEN** the `zebra-agent-web` unit suite runs with `ZEBRA_TEST_DB_ENGINE=postgresql`
- **THEN** it passes

### Requirement: Server backends recover dead connections
The Oracle and PostgreSQL backends SHALL, before reusing a connection that has seen an error
outside an atomic block, check that it is usable and replace it if not, so that worker threads and
the daemon (which never see request signals) do not reuse a closed connection.

#### Scenario: Server closed the connection
- **WHEN** the server terminates a connection and the next ORM call on it fails
- **THEN** the following ORM call on that thread opens a new connection and succeeds

#### Scenario: Inside a transaction
- **WHEN** a connection has seen an error inside an atomic block
- **THEN** it is not probed or replaced until the block ends
