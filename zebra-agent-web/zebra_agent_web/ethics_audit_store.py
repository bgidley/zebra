"""Django ORM implementation of the EthicsAuditStore interface."""

from __future__ import annotations

import logging
from datetime import datetime

from asgiref.sync import sync_to_async
from zebra_agent.storage.interfaces import EthicsAuditEntry, EthicsAuditStore

logger = logging.getLogger(__name__)


def _to_entry(row) -> EthicsAuditEntry:  # type: ignore[no-untyped-def]
    return EthicsAuditEntry(
        id=row.id,
        process_id=row.process_id,
        goal=row.goal,
        approved=row.approved,
        overall_reasoning=row.overall_reasoning,
        check_type=row.check_type,
        user_id=row.user_id,
        evaluated_at=row.evaluated_at,
    )


class DjangoEthicsAuditStore(EthicsAuditStore):
    """Oracle-backed ethics audit store via Django ORM.

    Entries are written once and never updated or deleted.
    """

    def __init__(self) -> None:
        self._initialized = False

    async def initialize(self) -> None:
        self._initialized = True
        logger.info("DjangoEthicsAuditStore initialized")

    async def close(self) -> None:
        pass

    async def append(self, entry: EthicsAuditEntry) -> None:
        @sync_to_async(thread_sensitive=False)
        def _insert() -> None:
            from zebra_agent_web.api.models import EthicsAuditEntryModel

            EthicsAuditEntryModel.objects.create(
                id=entry.id,
                process_id=entry.process_id,
                goal=entry.goal[:500],
                approved=entry.approved,
                overall_reasoning=entry.overall_reasoning,
                check_type=entry.check_type,
                user_id=entry.user_id,
                evaluated_at=entry.evaluated_at,
            )

        await _insert()

    async def list_entries(
        self,
        approved: bool | None = None,
        process_id: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EthicsAuditEntry]:
        @sync_to_async(thread_sensitive=False)
        def _query() -> list[EthicsAuditEntry]:
            from zebra_agent_web.api.models import EthicsAuditEntryModel

            qs = EthicsAuditEntryModel.objects.order_by("-evaluated_at")
            if approved is not None:
                qs = qs.filter(approved=approved)
            if process_id is not None:
                qs = qs.filter(process_id=process_id)
            if from_date is not None:
                qs = qs.filter(evaluated_at__gte=from_date)
            if to_date is not None:
                qs = qs.filter(evaluated_at__lte=to_date)
            return [_to_entry(row) for row in qs[offset : offset + limit]]

        return await _query()

    async def get(self, entry_id: str) -> EthicsAuditEntry | None:
        @sync_to_async(thread_sensitive=False)
        def _get() -> EthicsAuditEntry | None:
            from zebra_agent_web.api.models import EthicsAuditEntryModel

            try:
                row = EthicsAuditEntryModel.objects.get(id=entry_id)
                return _to_entry(row)
            except EthicsAuditEntryModel.DoesNotExist:
                return None

        return await _get()
