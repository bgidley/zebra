"""Oracle backend that recovers from connections closed by the server.

Django only discards broken connections in ``close_old_connections()``, which
runs from the ``request_started``/``request_finished`` signals. Our stores run
ORM calls via ``sync_to_async(thread_sensitive=False)`` in thread-pool workers,
and the daemon serves no requests at all, so a connection that Oracle (or the
network) closed was reused forever, failing every query with DPY-4011/DPY-1001
until the process was restarted (#133).

This wrapper applies the same check lazily: before using a connection that has
seen an error, ping it and reconnect if it is dead.
"""

import logging

from django.db import DatabaseError
from django.db.backends.oracle import base

logger = logging.getLogger(__name__)


class DatabaseWrapper(base.DatabaseWrapper):
    def ensure_connection(self) -> None:
        """Drop a dead connection before (re)connecting, outside transactions."""
        if self.connection is not None and self.errors_occurred and not self.in_atomic_block:
            if self.is_usable():
                self.errors_occurred = False
            else:
                logger.warning("Oracle connection is no longer usable; reconnecting")
                try:
                    self.close()
                except DatabaseError:
                    # close() clears self.connection even when closing fails.
                    pass
        super().ensure_connection()
