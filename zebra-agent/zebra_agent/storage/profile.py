"""In-memory implementation of the ProfileStore interface.

Stores values-profile versions in dicts keyed by user. Data is lost when the
process exits — suitable for tests and ephemeral CLI usage.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import replace

from zebra_agent.profile import ValuesProfileVersion, _utc_now
from zebra_agent.storage.interfaces import ProfileStore

logger = logging.getLogger(__name__)


class InMemoryProfileStore(ProfileStore):
    """In-memory implementation of the values-profile store.

    Maintains an append-only list of ``ValuesProfileVersion`` per user, plus a
    pointer to each user's current (latest) version. Versions are immutable
    once stored.
    """

    def __init__(self) -> None:
        self._versions_by_user: dict[int, list[ValuesProfileVersion]] = {}
        self._versions_by_id: dict[str, ValuesProfileVersion] = {}
        self._initialized = False

    async def initialize(self) -> None:
        self._initialized = True
        logger.info("InMemoryProfileStore initialized")

    async def close(self) -> None:
        """No resources to release."""

    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            await self.initialize()

    async def get_current(self, user_id: int) -> ValuesProfileVersion | None:
        await self._ensure_initialized()
        versions = self._versions_by_user.get(user_id, [])
        return versions[-1] if versions else None

    async def get_version(self, version_id: str) -> ValuesProfileVersion | None:
        await self._ensure_initialized()
        return self._versions_by_id.get(version_id)

    async def save_version(
        self, user_id: int, version: ValuesProfileVersion
    ) -> ValuesProfileVersion:
        await self._ensure_initialized()
        existing = self._versions_by_user.setdefault(user_id, [])
        next_number = (existing[-1].version_number + 1) if existing else 1
        persisted = replace(
            version,
            id=str(uuid.uuid4()),
            version_number=next_number,
            created_at=_utc_now(),
        )
        existing.append(persisted)
        self._versions_by_id[persisted.id] = persisted
        return persisted
