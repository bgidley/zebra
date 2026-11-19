"""PostgreSQL backend that recovers from connections closed by the server (#305).

Same reconnect-on-error behaviour as the Oracle backend (#133); see
``zebra_agent_web.db_backends.reconnect``.
"""

from django.db.backends.postgresql import base

from zebra_agent_web.db_backends.reconnect import ReconnectOnErrorMixin


class DatabaseWrapper(ReconnectOnErrorMixin, base.DatabaseWrapper):
    pass
