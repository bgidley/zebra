"""Django ORM implementation of PersonalKnowledgeStore.

Stores personal knowledge entries (facts, preferences, relationships, routines,
skills, history) for individual users. Backs the KnowledgeEntryModel table.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from asgiref.sync import sync_to_async
from zebra_agent.storage.interfaces import PersonalKnowledgeStore

if TYPE_CHECKING:
    from zebra_agent.knowledge import KnowledgeEntry

logger = logging.getLogger(__name__)


def _to_dataclass(row) -> KnowledgeEntry:  # type: ignore[no-untyped-def]
    """Convert a KnowledgeEntryModel row to the dataclass."""
    from zebra_agent.knowledge import KnowledgeEntry

    return KnowledgeEntry(
        id=row.id,
        user_id=row.user_id,
        category=row.category,
        key=row.key,
        value=row.value,
        source=row.source,
        confidence=row.confidence,
        last_verified=row.last_verified,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class DjangoPersonalKnowledgeStore(PersonalKnowledgeStore):
    """Django ORM-backed PersonalKnowledgeStore.

    All ORM operations are wrapped with sync_to_async to avoid blocking
    the async event loop, consistent with other Django stores in this package.
    """

    def __init__(self) -> None:
        self._initialized = False

    async def initialize(self) -> None:
        self._initialized = True
        logger.info("DjangoPersonalKnowledgeStore initialized")

    async def close(self) -> None:
        """Django manages its own connections."""

    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            await self.initialize()

    async def add_entry(self, entry: KnowledgeEntry) -> None:
        await self._ensure_initialized()

        @sync_to_async
        def _create() -> None:
            from zebra_agent_web.api.models import KnowledgeEntryModel

            KnowledgeEntryModel.objects.create(
                id=entry.id,
                user_id=entry.user_id,
                category=entry.category,
                key=entry.key,
                value=entry.value,
                source=entry.source,
                confidence=entry.confidence,
                last_verified=entry.last_verified,
            )

        await _create()

    async def update_entry(self, entry: KnowledgeEntry) -> None:
        await self._ensure_initialized()

        @sync_to_async
        def _update() -> None:
            from zebra_agent_web.api.models import KnowledgeEntryModel

            KnowledgeEntryModel.objects.filter(id=entry.id).update(
                category=entry.category,
                key=entry.key,
                value=entry.value,
                source=entry.source,
                confidence=entry.confidence,
                last_verified=entry.last_verified,
                updated_at=datetime.now(UTC),
            )

        await _update()

    async def delete_entry(self, entry_id: str) -> bool:
        await self._ensure_initialized()

        @sync_to_async
        def _delete() -> bool:
            from zebra_agent_web.api.models import KnowledgeEntryModel

            deleted, _ = KnowledgeEntryModel.objects.filter(id=entry_id).delete()
            return deleted > 0

        return await _delete()

    async def get_entry(self, entry_id: str) -> KnowledgeEntry | None:
        await self._ensure_initialized()

        @sync_to_async
        def _fetch() -> KnowledgeEntry | None:
            from zebra_agent_web.api.models import KnowledgeEntryModel

            try:
                row = KnowledgeEntryModel.objects.get(id=entry_id)
                return _to_dataclass(row)
            except KnowledgeEntryModel.DoesNotExist:
                return None

        return await _fetch()

    async def get_entries(self, user_id: int, category: str | None = None) -> list[KnowledgeEntry]:
        await self._ensure_initialized()

        @sync_to_async
        def _fetch() -> list[KnowledgeEntry]:
            from zebra_agent_web.api.models import KnowledgeEntryModel

            qs = KnowledgeEntryModel.objects.filter(user_id=user_id)
            if category is not None:
                qs = qs.filter(category=category)
            qs = qs.order_by("-last_verified")
            return [_to_dataclass(row) for row in qs]

        return await _fetch()

    async def get_context_for_llm(self, user_id: int, limit: int = 50) -> str:
        entries = await self.get_entries(user_id)
        entries = entries[:limit]
        if not entries:
            return ""
        lines = [f"[{e.category}] {e.key}: {e.value}" for e in entries]
        return "\n".join(lines)
