"""#133 / #305: a connection closed by the server must be replaced, not reused forever.

Worker threads (``sync_to_async(thread_sensitive=False)``) and the daemon never
see request signals, so the backend itself must drop dead connections. The
Oracle and PostgreSQL backends share ``ReconnectOnErrorMixin``; each probes
liveness its own way (Oracle ``ping()``, PostgreSQL ``SELECT 1`` on a cursor).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import oracledb
import psycopg
import pytest
from django.db import connection
from zebra_agent_web.db_backends.oracle.base import DatabaseWrapper as OracleWrapper
from zebra_agent_web.db_backends.postgresql.base import DatabaseWrapper as PostgresWrapper


@dataclass
class Backend:
    engine: str
    wrapper_cls: Any
    error: type[Exception]

    def make_dead(self) -> MagicMock:
        dead = MagicMock(name="dead")
        dead.ping.side_effect = self.error("connection closed")
        dead.cursor.return_value.__enter__.return_value.execute.side_effect = self.error(
            "connection closed"
        )
        dead.close.side_effect = self.error("connection closed")
        return dead

    def probes(self, conn: MagicMock) -> int:
        """How many liveness probes were sent on ``conn``."""
        return conn.ping.call_count + conn.cursor.call_count


BACKENDS = [
    Backend("zebra_agent_web.db_backends.oracle", OracleWrapper, oracledb.DatabaseError),
    Backend("zebra_agent_web.db_backends.postgresql", PostgresWrapper, psycopg.OperationalError),
]


@pytest.fixture(params=BACKENDS, ids=["oracle", "postgresql"])
def backend(request) -> Backend:
    return request.param


@pytest.fixture
def wrapper(backend, django_db_blocker):
    settings_dict = {**connection.settings_dict, "ENGINE": backend.engine}
    w = backend.wrapper_cls(settings_dict)
    fresh = MagicMock(name="fresh")

    def _connect():
        w.connection = fresh

    w.connect = _connect
    w.fresh = fresh
    # No real database is touched: ``connect`` and the connections are fakes.
    with django_db_blocker.unblock():
        yield w


def test_dead_connection_after_error_is_replaced(wrapper, backend):
    wrapper.connection = backend.make_dead()
    wrapper.errors_occurred = True

    wrapper.ensure_connection()

    assert wrapper.connection is wrapper.fresh


def test_live_connection_after_error_is_kept(wrapper, backend):
    live = MagicMock(name="live")
    wrapper.connection = live
    wrapper.errors_occurred = True

    wrapper.ensure_connection()

    assert wrapper.connection is live
    assert wrapper.errors_occurred is False
    assert backend.probes(live) == 1


def test_no_probe_without_prior_error(wrapper, backend):
    live = MagicMock(name="live")
    wrapper.connection = live

    wrapper.ensure_connection()

    assert wrapper.connection is live
    assert backend.probes(live) == 0


def test_dead_connection_inside_atomic_block_is_left_alone(wrapper, backend):
    dead = backend.make_dead()
    wrapper.connection = dead
    wrapper.errors_occurred = True
    wrapper.in_atomic_block = True

    wrapper.ensure_connection()

    assert wrapper.connection is dead
    assert backend.probes(dead) == 0


@pytest.mark.django_db(transaction=True)
def test_live_postgres_session_terminated_by_server_is_replaced():
    """Real server-side close (#305 O4); runs only with ZEBRA_TEST_DB_ENGINE=postgresql."""
    if connection.vendor != "postgresql":
        pytest.skip("needs a PostgreSQL test database")
    from django.contrib.auth.models import User
    from django.db import Error

    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_backend_pid()")
        pid = cursor.fetchone()[0]
    s = connection.settings_dict
    with psycopg.connect(
        host=s["HOST"],
        port=s["PORT"],
        dbname=s["NAME"],
        user=s["USER"],
        password=s["PASSWORD"],
        autocommit=True,
    ) as other:
        other.execute("SELECT pg_terminate_backend(%s)", [pid])

    with pytest.raises(Error):
        User.objects.count()
    # The failed call marked the connection; the next one must reconnect, not reuse it.
    assert User.objects.count() == 0
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_backend_pid()")
        assert cursor.fetchone()[0] != pid


def test_settings_engine_path_loads_the_backend(backend):
    from django.db.utils import load_backend

    loaded = load_backend(backend.engine)

    assert loaded.DatabaseWrapper is backend.wrapper_cls
