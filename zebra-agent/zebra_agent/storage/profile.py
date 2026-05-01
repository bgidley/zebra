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
        # field -> slug -> {slug, label, description, status, usage_count}
        self._tags: dict[str, dict[str, dict]] = {}
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

    async def get_approved_tags(self, field: str) -> list[dict]:
        await self._ensure_initialized()
        field_tags = self._tags.get(field, {})
        return [
            {
                "slug": tag["slug"],
                "label": tag["label"],
                "description": tag.get("description", ""),
            }
            for tag in field_tags.values()
            if tag["status"] in {"seeded", "promoted"}
        ]

    async def record_confirmed_tags(self, field_to_tags: dict[str, list[dict[str, str]]]) -> None:
        await self._ensure_initialized()
        for field, tag_list in field_to_tags.items():
            field_tags = self._tags.setdefault(field, {})
            for tag in tag_list:
                slug = tag["slug"]
                label = tag.get("label", slug)
                description = tag.get("description", "")
                if slug in field_tags:
                    field_tags[slug]["usage_count"] += 1
                    # Refresh label/description if caller provided them
                    if label:
                        field_tags[slug]["label"] = label
                    if description:
                        field_tags[slug]["description"] = description
                else:
                    field_tags[slug] = {
                        "slug": slug,
                        "label": label,
                        "description": description,
                        "status": "candidate",
                        "usage_count": 1,
                    }

    def seed_tag(
        self,
        field: str,
        slug: str,
        label: str,
        description: str = "",
        status: str = "seeded",
    ) -> None:
        """Test helper: insert a tag without going through the candidate path."""
        field_tags = self._tags.setdefault(field, {})
        field_tags[slug] = {
            "slug": slug,
            "label": label,
            "description": description,
            "status": status,
            "usage_count": 0,
        }
