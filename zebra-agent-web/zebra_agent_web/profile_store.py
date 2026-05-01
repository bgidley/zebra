"""Django ORM implementation of the ProfileStore interface.

The values-profile store is per-user and versioned. Each save_version call
creates a new ``ValuesProfileVersionModel`` with a monotonically increasing
``version_number`` per user, atomically updating the parent
``ValuesProfileModel.current_version`` pointer.
"""

from __future__ import annotations

import logging
import uuid

from asgiref.sync import sync_to_async
from django.db import transaction
from zebra_agent.profile import ValuesProfileVersion
from zebra_agent.storage.interfaces import ProfileStore

logger = logging.getLogger(__name__)


def _to_dataclass(row) -> ValuesProfileVersion:  # type: ignore[no-untyped-def]
    """Convert a ``ValuesProfileVersionModel`` row to the dataclass."""
    return ValuesProfileVersion(
        id=row.id,
        version_number=row.version_number,
        created_at=row.created_at,
        created_via=row.created_via,
        core_values_text=row.core_values_text,
        core_values_tags=list(row.core_values_tags or []),
        ethical_positions_text=row.ethical_positions_text,
        ethical_positions_tags=list(row.ethical_positions_tags or []),
        priorities_text=row.priorities_text,
        priorities_tags=list(row.priorities_tags or []),
        deal_breakers_text=row.deal_breakers_text,
        deal_breakers_tags=list(row.deal_breakers_tags or []),
        tags_extracted_at=row.tags_extracted_at,
        tags_extraction_model=row.tags_extraction_model,
    )


class DjangoProfileStore(ProfileStore):
    """Django ORM-backed ``ProfileStore``.

    Mirrors ``InMemoryProfileStore`` semantics: append-only versions, monotonic
    ``version_number``, and a per-user current pointer. Saves are wrapped in a
    transaction so the ``current_version`` update is consistent with the new
    version row.
    """

    def __init__(self) -> None:
        self._initialized = False

    async def initialize(self) -> None:
        self._initialized = True
        logger.info("DjangoProfileStore initialized")

    async def close(self) -> None:
        """Django manages its own connections."""

    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            await self.initialize()

    async def get_current(self, user_id: int) -> ValuesProfileVersion | None:
        await self._ensure_initialized()

        @sync_to_async
        def _fetch() -> ValuesProfileVersion | None:
            from zebra_agent_web.api.models import ValuesProfileModel

            try:
                profile = ValuesProfileModel.objects.select_related("current_version").get(
                    user_id=user_id
                )
            except ValuesProfileModel.DoesNotExist:
                return None
            if profile.current_version is None:
                return None
            return _to_dataclass(profile.current_version)

        return await _fetch()

    async def get_version(self, version_id: str) -> ValuesProfileVersion | None:
        await self._ensure_initialized()

        @sync_to_async
        def _fetch() -> ValuesProfileVersion | None:
            from zebra_agent_web.api.models import ValuesProfileVersionModel

            try:
                row = ValuesProfileVersionModel.objects.get(id=version_id)
            except ValuesProfileVersionModel.DoesNotExist:
                return None
            return _to_dataclass(row)

        return await _fetch()

    async def save_version(
        self, user_id: int, version: ValuesProfileVersion
    ) -> ValuesProfileVersion:
        await self._ensure_initialized()

        @sync_to_async
        def _save() -> ValuesProfileVersion:
            from django.db.models import Max

            from zebra_agent_web.api.models import (
                ValuesProfileModel,
                ValuesProfileVersionModel,
            )

            with transaction.atomic():
                profile, _ = ValuesProfileModel.objects.get_or_create(
                    user_id=user_id,
                    defaults={"id": str(uuid.uuid4())},
                )

                current_max = (
                    ValuesProfileVersionModel.objects.filter(profile=profile).aggregate(
                        max_v=Max("version_number")
                    )["max_v"]
                    or 0
                )
                next_number = current_max + 1

                row = ValuesProfileVersionModel.objects.create(
                    id=str(uuid.uuid4()),
                    profile=profile,
                    version_number=next_number,
                    created_via=version.created_via,
                    core_values_text=version.core_values_text,
                    core_values_tags=list(version.core_values_tags),
                    ethical_positions_text=version.ethical_positions_text,
                    ethical_positions_tags=list(version.ethical_positions_tags),
                    priorities_text=version.priorities_text,
                    priorities_tags=list(version.priorities_tags),
                    deal_breakers_text=version.deal_breakers_text,
                    deal_breakers_tags=list(version.deal_breakers_tags),
                    tags_extracted_at=version.tags_extracted_at,
                    tags_extraction_model=version.tags_extraction_model,
                )

                profile.current_version = row
                profile.save(update_fields=["current_version", "updated_at"])

                return _to_dataclass(row)

        return await _save()

    async def get_approved_tags(self, field: str) -> list[dict]:
        await self._ensure_initialized()

        @sync_to_async
        def _fetch() -> list[dict]:
            from zebra_agent_web.api.models import ValuesTagModel

            rows = ValuesTagModel.objects.filter(
                field=field, status__in=["seeded", "promoted"]
            ).values("slug", "label", "description")
            return list(rows)

        return await _fetch()

    async def record_confirmed_tags(self, field_to_tags: dict[str, list[dict[str, str]]]) -> None:
        await self._ensure_initialized()

        @sync_to_async
        def _record() -> None:
            from django.db.models import F

            from zebra_agent_web.api.models import ValuesTagModel

            with transaction.atomic():
                for field, tag_list in field_to_tags.items():
                    for tag in tag_list:
                        slug = tag["slug"]
                        label = tag.get("label", slug)
                        description = tag.get("description", "")

                        existing = ValuesTagModel.objects.filter(field=field, slug=slug).first()
                        if existing is None:
                            ValuesTagModel.objects.create(
                                id=str(uuid.uuid4()),
                                field=field,
                                slug=slug,
                                label=label,
                                description=description,
                                status="candidate",
                                usage_count=1,
                            )
                        else:
                            ValuesTagModel.objects.filter(pk=existing.pk).update(
                                usage_count=F("usage_count") + 1,
                                **({"label": label} if label and label != existing.label else {}),
                            )

        await _record()
