"""#305: the database backend is chosen explicitly, Oracle stays the default with ORACLE_DSN."""

from __future__ import annotations

import os
import runpy
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured
from zebra_agent_web.db_config import database_config, db_engine

SQLITE_PATH = Path("/tmp/zebra-test.sqlite3")


def test_unset_without_oracle_dsn_is_sqlite():
    assert database_config({}, SQLITE_PATH) == {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": SQLITE_PATH,
    }


def test_unset_with_oracle_dsn_is_oracle_as_before():
    env = {"ORACLE_DSN": "dsn", "ORACLE_USERNAME": "u", "ORACLE_PASSWORD": "p"}

    assert database_config(env, SQLITE_PATH) == {
        "ENGINE": "zebra_agent_web.db_backends.oracle",
        "NAME": "dsn",
        "USER": "u",
        "PASSWORD": "p",
    }


@pytest.mark.parametrize("value", ["postgresql", "postgres", " PostgreSQL "])
def test_postgresql_reads_libpq_variables(value):
    env = {
        "ZEBRA_DB_ENGINE": value,
        "PGHOST": "db.example",
        "PGPORT": "6543",
        "PGDATABASE": "zeb",
        "PGUSER": "zu",
        "PGPASSWORD": "secret",
        # Postgres wins over a leftover ORACLE_DSN when chosen explicitly.
        "ORACLE_DSN": "ignored",
    }

    assert database_config(env, SQLITE_PATH) == {
        "ENGINE": "zebra_agent_web.db_backends.postgresql",
        "NAME": "zeb",
        "USER": "zu",
        "PASSWORD": "secret",
        "HOST": "db.example",
        "PORT": "6543",
    }


def test_postgresql_defaults():
    config = database_config({"ZEBRA_DB_ENGINE": "postgresql"}, SQLITE_PATH)

    assert config["NAME"] == "zebra"
    assert config["USER"] == "zebra"
    assert config["HOST"] == "localhost"
    assert config["PORT"] == "5432"


def test_explicit_sqlite_ignores_oracle_dsn():
    assert db_engine({"ZEBRA_DB_ENGINE": "sqlite", "ORACLE_DSN": "dsn"}) == "sqlite"


def test_explicit_oracle():
    assert db_engine({"ZEBRA_DB_ENGINE": "oracle"}) == "oracle"


def test_unknown_engine_fails_loudly():
    with pytest.raises(ImproperlyConfigured, match="mysql"):
        db_engine({"ZEBRA_DB_ENGINE": "mysql"})


@pytest.mark.parametrize("value", ["mysql", "oracle", "postgress"])
def test_unit_settings_refuse_an_unusable_test_engine(monkeypatch, value):
    """A misspelt ZEBRA_TEST_DB_ENGINE must not silently run the suite on SQLite."""
    import zebra_agent_web.test_settings as test_settings

    monkeypatch.setenv("ZEBRA_TEST_DB_ENGINE", value)
    with pytest.raises(ImproperlyConfigured):
        runpy.run_path(test_settings.__file__)


@pytest.mark.django_db
def test_unit_suite_runs_on_the_requested_engine():
    """With ZEBRA_TEST_DB_ENGINE=postgresql the suite really runs on psycopg 3 (#305 O1)."""
    from django.db import connection

    requested = os.environ.get("ZEBRA_TEST_DB_ENGINE", "").strip().lower()
    if requested in ("postgresql", "postgres"):
        from django.db.backends.postgresql.psycopg_any import is_psycopg3

        assert connection.vendor == "postgresql"
        assert is_psycopg3
        assert connection.settings_dict["ENGINE"] == "zebra_agent_web.db_backends.postgresql"
    else:
        assert connection.vendor == "sqlite"
