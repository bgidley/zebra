## Context

`settings.py` chose the database with `if ORACLE_DSN: oracle else sqlite`. Oracle is prod (ADB
26ai), SQLite is unit tests only. #311 adds PostgreSQL + pgvector as a second hosting target; this
change (#305) is its foundation. The ORM is almost all portable; the Oracle-only parts are vector
embeddings (`embeddings.py`, migrations 0026/0028: already no-ops off Oracle), the #133 reconnect
wrapper, and the CLI's backend guard.

## Goals / Non-Goals

**Goals:** Postgres as a full server backend (migrations, stores, CLI, daemon); explicit,
fail-loud backend selection; reconnect parity; a way to run the unit suite on Postgres.

**Non-Goals:** pgvector search (#306), deployment units (#307/#310), CI job (#308), data copy
(#309), `DATABASE_URL` parsing (libpq variables are enough and add no dependency).

## Decisions

- **`ZEBRA_DB_ENGINE` with a backward-compatible default.** Prod sets `ORACLE_DSN` and nothing
  else; it must resolve to exactly the same `DATABASES` dict. An explicit engine wins over a
  leftover `ORACLE_DSN`. Unknown values raise, because a mistyped engine falling through to SQLite
  would start a broken Zebra.
- **libpq variables (`PG*`)** rather than a URL: standard, understood by `psql`/`pg_dump` too, and
  libpq reads `PGSSLMODE` etc. itself.
- **A shared `ReconnectOnErrorMixin`** instead of a second copy. Django's `CONN_HEALTH_CHECKS`
  is not enough: like `close_old_connections`, it runs only from request signals, which worker
  threads and the daemon never see (#133). Liveness probing stays the vendor's `is_usable()`
  (Oracle `ping()`, Postgres `SELECT 1`).
- **Postgres unit runs via `ZEBRA_TEST_DB_ENGINE`** in `test_settings`, so the same tests run on
  both. SQLite stays the default for speed. CI wiring is #308.

## Risks / Trade-offs

- Tests may encode SQLite or Oracle behaviour (ordering without `ORDER BY`, `""` vs `NULL`,
  case-sensitive `LIKE`, sequence values after explicit ids). Fixed where found; each fix keeps
  Oracle and SQLite behaviour.
- Found by the first Postgres run: `Sum` over a boolean (Postgres has no `sum(boolean)`), and
  tests whose fixture data sat in an uncommitted transaction while the view read on a
  worker-thread connection: on Postgres that is a lock wait forever (SQLite's shared in-memory
  database hides it). The CI job sets `lock_timeout` so such a wait fails instead of hanging.
- Rootless Podman on the prod host has no `cpu` cgroup controller: containers there can be
  memory-capped but not CPU-capped (relevant to #307/#308).
- psycopg binary wheels: available for linux aarch64/x86_64 and macOS, so the image needs no libpq.
