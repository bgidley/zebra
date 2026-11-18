"""Oracle backend that recovers from connections closed by the server (#133).

See ``zebra_agent_web.db_backends.reconnect`` for why this is needed.
"""

from django.db.backends.oracle import base

from zebra_agent_web.db_backends.reconnect import ReconnectOnErrorMixin


class DatabaseWrapper(ReconnectOnErrorMixin, base.DatabaseWrapper):
    pass
