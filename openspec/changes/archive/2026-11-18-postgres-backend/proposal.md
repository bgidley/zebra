## Why

Zebra can only run as a real instance on Oracle Autonomous Database: settings pick Oracle when
`ORACLE_DSN` is set and fall back to SQLite otherwise, and SQLite cannot run a live Zebra
(locking). To deploy Zebra on alternative, non-OCI hosting (tracking #311) it needs a second
server backend. PostgreSQL (with pgvector, used by #306) is that backend. This change (#305) makes
Zebra run on PostgreSQL 16+. Vector memory search stays Oracle-only here and falls back to keyword
ranking on Postgres until #306.

## What Changes

- **Explicit backend selection** (`zebra_agent_web/db_config.py`): `ZEBRA_DB_ENGINE` =
  `oracle` | `postgresql` (alias `postgres`) | `sqlite`. Unset keeps today's behaviour (Oracle when
  `ORACLE_DSN` is set, else SQLite). An unknown value raises `ImproperlyConfigured`. PostgreSQL
  reads the libpq variables `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`.
- **`psycopg[binary]>=3.2`** added to `zebra-agent-web` (`oracledb` kept).
- **Reconnect on error for both backends**: the #133 logic moves into
  `db_backends/reconnect.py` (`ReconnectOnErrorMixin`). `db_backends/oracle` and a new
  `db_backends/postgresql` use it, so a connection the server closed is replaced in worker threads
  and the daemon too.
- **CLI**: `zebra goal` / `zebra goals` accept PostgreSQL as a server backend (as well as Oracle).
  Only SQLite still needs `--allow-sqlite`.
- **Unit suite on Postgres**: `ZEBRA_TEST_DB_ENGINE=postgresql` points `test_settings` at
  PostgreSQL. Tests and code that only worked on SQLite/Oracle are fixed so that the whole web
  unit suite passes on Postgres, SQLite and (e2e) Oracle.
- **Docs**: settings tables, `specs/zebra-as-is.md` storage section.

Not in scope: pgvector embeddings (#306), test stack quadlets (#307), CI Postgres job (#308), data
copy (#309), deploy bundle (#310).

## Capabilities

### New Capabilities
- `database-backends`: selecting the database backend, PostgreSQL as a supported server backend,
  reconnect-on-error for server backends.

### Modified Capabilities
- `cli-persistent-store`: the CLI accepts PostgreSQL as well as Oracle without `--allow-sqlite`.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | Zebra's schema and stores work on PostgreSQL 16 + pgvector, and stay working | A `unit-postgres` CI job runs `migrate` from empty and the whole `zebra-agent-web` unit suite on the `pgvector/pgvector:pg16` image, on the psycopg 3 backend (a test asserts `connection.vendor == "postgresql"` there), with no Postgres-only skips except the documented Oracle-only ones; green on the branch and on master |
| O2 | Prod on Oracle is unchanged | With `ORACLE_DSN` set and no `ZEBRA_DB_ENGINE`, settings resolve to the same Oracle backend (unit test); the master pipeline's Oracle e2e, deploy and smoke stay green and prod serves the new build |
| O3 | The backend choice is explicit and a misspelt choice never silently lands on SQLite | `ZEBRA_DB_ENGINE` selects oracle/postgresql/sqlite; an unknown value fails at start-up, and so does an unknown `ZEBRA_TEST_DB_ENGINE` (unit tests) |
| O4 | A Postgres connection the server closed is replaced, not reused forever (#133 parity) | Reconnect unit tests run for both backends, plus a live Postgres test (in `unit-postgres`) that terminates its own backend session and the next ORM call succeeds on a new session |
| O5 | Zebra does real work against Postgres outside the tests | With no Oracle variables set, `zebra goals` queries Postgres and exits 0, and `manage.py run_daemon` completes DB-backed cycles (routine processes created and completed in Postgres) (output on #305) |

Zebra's outcome feedback (2026-11-16) was taken except one point: failing start-up when neither
`ZEBRA_DB_ENGINE` nor `ORACLE_DSN` is set. SQLite stays the default for unit tests, dev and image
builds (backward compatibility); the CLI guard still refuses SQLite for goals.
