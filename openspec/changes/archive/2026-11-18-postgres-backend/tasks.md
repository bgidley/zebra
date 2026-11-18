> Branch: `f305/postgres-backend`. Commit with `Part of #305`, final `Closes #305`. Tracking: #311.

## 1. Backend selection

- [x] 1.1 `zebra_agent_web/db_config.py`: `db_engine()`, `database_config()` (`ZEBRA_DB_ENGINE`, libpq vars, fail-loud)
- [x] 1.2 `settings.py` uses it; `test_settings.py` honours `ZEBRA_TEST_DB_ENGINE=postgresql`
- [x] 1.3 `psycopg[binary]>=3.2` dependency
- [x] 1.4 Tests: `test_db_config.py`

## 2. Reconnect parity

- [x] 2.1 `db_backends/reconnect.py` `ReconnectOnErrorMixin`; Oracle backend uses it; new `db_backends/postgresql`
- [x] 2.2 `test_db_reconnect.py` parametrised over both backends
- [x] 2.3 Live Postgres test: terminate own backend session, next ORM call succeeds (skips off Postgres)

## 3. CLI

- [x] 3.1 `_check_backend` accepts `postgresql`; message names `ZEBRA_DB_ENGINE=postgresql`
- [x] 3.2 Tests

## 4. Postgres parity

- [x] 4.1 `migrate` from empty on `pgvector/pgvector:pg16`
- [x] 4.2 Whole web unit suite passes with `ZEBRA_TEST_DB_ENGINE=postgresql`; fixed: `get_all_stats` `Sum("success")` → conditional `Count` (no `sum(boolean)` on Postgres); `/dreams/` page tests made `transaction=True` (worker-thread connection blocked on the test's uncommitted `SystemStateModel` row)
- [x] 4.3 `zebra goals` and `manage.py run_daemon` do DB-backed work against Postgres with no Oracle vars
- [x] 4.4 Unknown `ZEBRA_TEST_DB_ENGINE` fails; test asserts the suite really runs on psycopg 3 (Zebra feedback)
- [x] 4.5 CI `unit-postgres` job: throwaway pinned `pgvector/pg16` container, `migrate`, web unit suite, `lock_timeout` so lock waits fail instead of hanging

## 5. Docs

- [x] 5.1 `AGENTS.md` / `zebra-agent-web/AGENTS.md` settings; `specs/zebra-as-is.md` storage section; `README-CICD.md` job table
