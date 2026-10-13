"""#133: a connection closed by Oracle must be replaced, not reused forever.

Worker threads (``sync_to_async(thread_sensitive=False)``) and the daemon never
see request signals, so the backend itself must drop dead connections.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import oracledb
import pytest
from django.db import connection
from zebra_agent_web.db_backends.oracle.base import DatabaseWrapper


@pytest.fixture
def wrapper(django_db_blocker):
    settings_dict = {**connection.settings_dict, "ENGINE": "zebra_agent_web.db_backends.oracle"}
    w = DatabaseWrapper(settings_dict)
    fresh = MagicMock(name="fresh")

    def _connect():
        w.connection = fresh

    w.connect = _connect
    w.fresh = fresh
    # No real database is touched: ``connect`` and the connections are fakes.
    with django_db_blocker.unblock():
        yield w


def _dead_connection() -> MagicMock:
    dead = MagicMock(name="dead")
    dead.ping.side_effect = oracledb.DatabaseError("DPY-4011")
    dead.close.side_effect = oracledb.DatabaseError("DPY-4011")
    return dead


def test_dead_connection_after_error_is_replaced(wrapper):
    wrapper.connection = _dead_connection()
    wrapper.errors_occurred = True

    wrapper.ensure_connection()

    assert wrapper.connection is wrapper.fresh


def test_live_connection_after_error_is_kept(wrapper):
    live = MagicMock(name="live")
    wrapper.connection = live
    wrapper.errors_occurred = True

    wrapper.ensure_connection()

    assert wrapper.connection is live
    assert wrapper.errors_occurred is False
    live.ping.assert_called_once()


def test_no_ping_without_prior_error(wrapper):
    live = MagicMock(name="live")
    wrapper.connection = live

    wrapper.ensure_connection()

    assert wrapper.connection is live
    live.ping.assert_not_called()


def test_dead_connection_inside_atomic_block_is_left_alone(wrapper):
    dead = _dead_connection()
    wrapper.connection = dead
    wrapper.errors_occurred = True
    wrapper.in_atomic_block = True

    wrapper.ensure_connection()

    assert wrapper.connection is dead
    dead.ping.assert_not_called()


def test_settings_engine_path_loads_the_backend():
    from django.db.utils import load_backend

    backend = load_backend("zebra_agent_web.db_backends.oracle")

    assert backend.DatabaseWrapper is DatabaseWrapper
