"""In-memory implementation of the EthicsAuditStore interface."""

from __future__ import annotations

import logging
from datetime import datetime

from zebra_agent.storage.interfaces import EthicsAuditEntry, EthicsAuditStore

logger = logging.getLogger(__name__)


class InMemoryEthicsAuditStore(EthicsAuditStore):
    """In-memory, append-only ethics audit log.

    Suitable for testing and standalone CLI use. Data is lost on process exit.
    """

    def __init__(self) -> None:
        self._entries: list[EthicsAuditEntry] = []
        self._initialized = False

    async def initialize(self) -> None:
        self._initialized = True
        logger.info("InMemoryEthicsAuditStore initialized")

    async def close(self) -> None:
        pass

    async def append(self, entry: EthicsAuditEntry) -> None:
        self._entries.append(entry)

    async def list_entries(
        self,
        approved: bool | None = None,
        process_id: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EthicsAuditEntry]:
        results = list(self._entries)

        if approved is not None:
            results = [e for e in results if e.approved == approved]
        if process_id is not None:
            results = [e for e in results if e.process_id == process_id]
        if from_date is not None:
            results = [e for e in results if e.evaluated_at >= from_date]
        if to_date is not None:
            results = [e for e in results if e.evaluated_at <= to_date]

        results.sort(key=lambda e: e.evaluated_at, reverse=True)
        return results[offset : offset + limit]

    async def get(self, entry_id: str) -> EthicsAuditEntry | None:
        for entry in self._entries:
            if entry.id == entry_id:
                return entry
        return None
