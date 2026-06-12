"""Django ORM implementation of the TrustStore interface (F12 / REQ-TRUST-001)."""

from __future__ import annotations

import logging

from asgiref.sync import sync_to_async
from zebra_agent.storage.interfaces import TrustStore
from zebra_agent.storage.trust import (
    SUGGESTION_APPROVED,
    SUGGESTION_PENDING,
    SUGGESTION_REJECTED,
    TrustChangeRecord,
    TrustLevel,
    TrustSuggestion,
    approval_reason,
    list_domains,
    validate_domain,
)

logger = logging.getLogger(__name__)


def _to_record(row) -> TrustChangeRecord:  # type: ignore[no-untyped-def]
    return TrustChangeRecord(
        id=row.id,
        user_id=row.user_id,
        domain=row.domain,
        old_level=TrustLevel(row.old_level),
        new_level=TrustLevel(row.new_level),
        reason=row.reason,
        changed_by=row.changed_by,
        changed_at=row.changed_at,
    )


def _set_level_sync(
    user_id: int, domain: str, level: TrustLevel, reason: str, changed_by: str
) -> TrustChangeRecord:
    """Upsert the level row and append the audit record (call inside a transaction)."""
    from zebra_agent_web.api.models import TrustChangeModel, TrustLevelModel

    row = TrustLevelModel.objects.filter(user_id=user_id, domain=domain).first()
    old_level = TrustLevel(row.level) if row else TrustLevel.SUPERVISED
    if row:
        row.level = level.value
        row.save(update_fields=["level", "updated_at"])
    else:
        TrustLevelModel.objects.create(user_id=user_id, domain=domain, level=level.value)
    record = TrustChangeRecord(
        user_id=user_id,
        domain=domain,
        old_level=old_level,
        new_level=level,
        reason=reason,
        changed_by=changed_by,
    )
    TrustChangeModel.objects.create(
        id=record.id,
        user_id=user_id,
        domain=domain,
        old_level=record.old_level.value,
        new_level=record.new_level.value,
        reason=reason,
        changed_by=changed_by,
        changed_at=record.changed_at,
    )
    logger.info(
        "Trust level for user %s domain %s: %s -> %s (%s)",
        user_id,
        domain,
        old_level,
        level,
        reason,
    )
    return record


def _to_suggestion(row) -> TrustSuggestion:  # type: ignore[no-untyped-def]
    return TrustSuggestion(
        id=row.id,
        user_id=row.user_id,
        domain=row.domain,
        to_level=TrustLevel(row.to_level),
        evidence=row.evidence,
        status=row.status,
        created_at=row.created_at,
        resolved_at=row.resolved_at,
        resolved_by=row.resolved_by,
    )


class DjangoTrustStore(TrustStore):
    """Oracle-backed trust store via Django ORM.

    Levels live in ``zebra_trust_levels`` (one row per explicitly-set
    (user, domain) pair); every change appends an immutable row to
    ``zebra_trust_changes`` in the same transaction.
    """

    async def initialize(self) -> None:
        logger.info("DjangoTrustStore initialized")

    async def close(self) -> None:
        pass

    async def get_trust_level(self, user_id: int, domain: str) -> TrustLevel:
        @sync_to_async(thread_sensitive=False)
        def _get() -> str | None:
            from zebra_agent_web.api.models import TrustLevelModel

            row = TrustLevelModel.objects.filter(user_id=user_id, domain=domain).first()
            return row.level if row else None

        level = await _get()
        return TrustLevel(level) if level else TrustLevel.SUPERVISED

    async def set_trust_level(
        self,
        user_id: int,
        domain: str,
        level: TrustLevel,
        reason: str,
        changed_by: str,
    ) -> TrustChangeRecord:
        validate_domain(domain)

        @sync_to_async(thread_sensitive=False)
        def _set() -> TrustChangeRecord:
            from django.db import transaction

            with transaction.atomic():
                record = _set_level_sync(user_id, domain, level, reason, changed_by)
            return record

        return await _set()

    async def get_all_trust_levels(self, user_id: int) -> dict[str, TrustLevel]:
        @sync_to_async(thread_sensitive=False)
        def _query() -> dict[str, str]:
            from zebra_agent_web.api.models import TrustLevelModel

            return dict(
                TrustLevelModel.objects.filter(user_id=user_id).values_list("domain", "level")
            )

        stored = await _query()
        levels = {domain: TrustLevel.SUPERVISED for domain in list_domains()}
        for domain, level in stored.items():
            levels[domain] = TrustLevel(level)
        return levels

    async def list_trust_changes(
        self, user_id: int, domain: str | None = None
    ) -> list[TrustChangeRecord]:
        @sync_to_async(thread_sensitive=False)
        def _query() -> list[TrustChangeRecord]:
            from zebra_agent_web.api.models import TrustChangeModel

            qs = TrustChangeModel.objects.filter(user_id=user_id).order_by("-changed_at")
            if domain is not None:
                qs = qs.filter(domain=domain)
            return [_to_record(row) for row in qs]

        return await _query()

    async def add_suggestion(
        self, user_id: int, domain: str, to_level: TrustLevel, evidence: str
    ) -> TrustSuggestion:
        validate_domain(domain)
        to_level = TrustLevel(to_level)

        @sync_to_async(thread_sensitive=False)
        def _insert() -> TrustSuggestion:
            from zebra_agent_web.api.models import TrustSuggestionModel

            suggestion = TrustSuggestion(
                user_id=user_id, domain=domain, to_level=to_level, evidence=evidence
            )
            TrustSuggestionModel.objects.create(
                id=suggestion.id,
                user_id=user_id,
                domain=domain,
                to_level=to_level.value,
                evidence=evidence,
                status=suggestion.status,
                created_at=suggestion.created_at,
            )
            logger.info(
                "Trust suggestion for user %s domain %s -> %s queued", user_id, domain, to_level
            )
            return suggestion

        return await _insert()

    async def list_suggestions(
        self, user_id: int, status: str | None = None
    ) -> list[TrustSuggestion]:
        @sync_to_async(thread_sensitive=False)
        def _query() -> list[TrustSuggestion]:
            from zebra_agent_web.api.models import TrustSuggestionModel

            qs = TrustSuggestionModel.objects.filter(user_id=user_id).order_by("-created_at")
            if status is not None:
                qs = qs.filter(status=status)
            return [_to_suggestion(row) for row in qs]

        return await _query()

    async def resolve_suggestion(
        self, suggestion_id: str, approve: bool, resolved_by: str
    ) -> TrustSuggestion:
        @sync_to_async(thread_sensitive=False)
        def _resolve() -> TrustSuggestion:
            from django.db import transaction
            from django.utils import timezone

            from zebra_agent_web.api.models import TrustSuggestionModel

            with transaction.atomic():
                row = (
                    TrustSuggestionModel.objects.select_for_update()
                    .filter(id=suggestion_id)
                    .first()
                )
                if row is None:
                    raise ValueError(f"Unknown trust suggestion {suggestion_id!r}")
                if row.status != SUGGESTION_PENDING:
                    raise ValueError(f"Trust suggestion {suggestion_id!r} is already {row.status}")
                if approve:
                    _set_level_sync(
                        row.user_id,
                        row.domain,
                        TrustLevel(row.to_level),
                        reason=approval_reason(row.evidence),
                        changed_by=resolved_by,
                    )
                row.status = SUGGESTION_APPROVED if approve else SUGGESTION_REJECTED
                row.resolved_at = timezone.now()
                row.resolved_by = resolved_by
                row.save(update_fields=["status", "resolved_at", "resolved_by"])
                return _to_suggestion(row)

        return await _resolve()
