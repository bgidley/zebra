"""Django ORM implementation of PersonalKnowledgeStore.

Stores personal knowledge entries (facts, preferences, relationships, routines,
skills, history) for individual users. Backs the KnowledgeEntryModel table.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
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
        time_sensitive=row.time_sensitive,
        deleted_at=row.deleted_at,
    )


class DjangoPersonalKnowledgeStore(PersonalKnowledgeStore):
    """Django ORM-backed PersonalKnowledgeStore.

    All ORM operations are wrapped with sync_to_async(thread_sensitive=False),
    consistent with other Django stores in this package. Goals call the store
    after the request that started them has returned, so a thread-sensitive
    call would hit that request's finished CurrentThreadExecutor (#123).
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

        @sync_to_async(thread_sensitive=False)
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
                time_sensitive=entry.time_sensitive,
            )

        await _create()

    async def update_entry(self, entry: KnowledgeEntry) -> None:
        await self._ensure_initialized()

        @sync_to_async(thread_sensitive=False)
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
                time_sensitive=entry.time_sensitive,
            )

        await _update()

    async def soft_delete_entry(self, entry_id: str) -> bool:
        await self._ensure_initialized()

        @sync_to_async(thread_sensitive=False)
        def _soft_delete() -> bool:
            from zebra_agent_web.api.models import KnowledgeEntryModel

            updated = KnowledgeEntryModel.objects.filter(
                id=entry_id, deleted_at__isnull=True
            ).update(deleted_at=datetime.now(UTC))
            return updated > 0

        return await _soft_delete()

    async def get_entry(self, entry_id: str) -> KnowledgeEntry | None:
        await self._ensure_initialized()

        @sync_to_async(thread_sensitive=False)
        def _fetch() -> KnowledgeEntry | None:
            from zebra_agent_web.api.models import KnowledgeEntryModel

            try:
                row = KnowledgeEntryModel.objects.get(id=entry_id)
                return _to_dataclass(row)
            except KnowledgeEntryModel.DoesNotExist:
                return None

        return await _fetch()

    async def get_entries(
        self,
        user_id: int,
        category: str | None = None,
        include_deleted: bool = False,
    ) -> list[KnowledgeEntry]:
        await self._ensure_initialized()

        @sync_to_async(thread_sensitive=False)
        def _fetch() -> list[KnowledgeEntry]:
            from zebra_agent_web.api.models import KnowledgeEntryModel

            qs = KnowledgeEntryModel.objects.filter(user_id=user_id)
            if not include_deleted:
                qs = qs.filter(deleted_at__isnull=True)
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

    async def search_entries(
        self, user_id: int, query: str, limit: int = 20
    ) -> list[KnowledgeEntry]:
        """The user's entries nearest to ``query`` by in-database embedding (Oracle, #169).

        Falls back to keyword ranking when vector search is unavailable or fails.
        """
        await self._ensure_initialized()

        @sync_to_async(thread_sensitive=False)
        def _search() -> list[KnowledgeEntry] | None:
            from zebra_agent_web import embeddings
            from zebra_agent_web.api.models import KnowledgeEntryModel

            if not query or not query.strip() or not embeddings.vector_search_ready():
                return None
            try:
                ids = embeddings.nearest_ids(
                    "zebra_knowledge_entries",
                    query,
                    limit,
                    # Bind names must not be Oracle reserved words (UID → ORA-01745).
                    where="t.user_id = %(owner_id)s AND t.deleted_at IS NULL",
                    params={"owner_id": user_id},
                )
            except Exception as e:  # noqa: BLE001 - retrieval must degrade, not fail the goal
                logger.warning("Vector knowledge search failed, using keyword ranking: %s", e)
                return None
            rows = {r.id: r for r in KnowledgeEntryModel.objects.filter(id__in=ids)}
            return [_to_dataclass(rows[i]) for i in ids if i in rows]

        found = await _search()
        if found is None:
            return await super().search_entries(user_id, query, limit)
        return found

    async def get_entries_for_verification(
        self,
        user_id: int,
        low_confidence_threshold: float = 0.6,
        max_age_days: int = 90,
        max_entries: int = 5,
    ) -> list[KnowledgeEntry]:
        await self._ensure_initialized()

        @sync_to_async(thread_sensitive=False)
        def _fetch() -> list[KnowledgeEntry]:
            from django.db.models import Q

            from zebra_agent_web.api.models import KnowledgeEntryModel

            cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
            qs = (
                KnowledgeEntryModel.objects.filter(
                    user_id=user_id,
                    deleted_at__isnull=True,
                )
                .filter(Q(confidence__lt=low_confidence_threshold) | Q(last_verified__lt=cutoff))
                .order_by("confidence")[:max_entries]
            )
            return [_to_dataclass(row) for row in qs]

        return await _fetch()

    async def find_contradicting_entry(
        self, user_id: int, category: str, key: str
    ) -> KnowledgeEntry | None:
        await self._ensure_initialized()

        @sync_to_async(thread_sensitive=False)
        def _fetch() -> KnowledgeEntry | None:
            from zebra_agent_web.api.models import KnowledgeEntryModel

            try:
                row = KnowledgeEntryModel.objects.get(
                    user_id=user_id,
                    category=category,
                    key=key,
                    deleted_at__isnull=True,
                )
                return _to_dataclass(row)
            except KnowledgeEntryModel.DoesNotExist:
                return None

        return await _fetch()
