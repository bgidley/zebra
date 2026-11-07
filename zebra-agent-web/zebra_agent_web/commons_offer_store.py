"""``DjangoOfferStore``: offers seen on the public Commons in ``WorkflowOfferModel`` (#232).

One row per content hash, owned by the Commons owner (REQ-USR-002). Status changes go through
``zebra_agent.commons.offers.check_transition``. ORM calls are
``sync_to_async(thread_sensitive=False)``: the exchange runs inside goal tasks and the daemon,
which outlive any request (#123).
"""

from __future__ import annotations

from typing import Any

from asgiref.sync import sync_to_async
from django.db import IntegrityError, transaction
from zebra_agent.commons.offers import OfferRecord, OfferStore, check_transition

from zebra_agent_web.api.models import WorkflowOfferModel


def _record(row: WorkflowOfferModel) -> OfferRecord:
    return OfferRecord(
        content_sha256=row.content_sha256,
        name=row.name,
        summary=row.summary,
        use_when=row.use_when,
        stats=dict(row.stats or {}),
        publisher_pubkey=row.publisher_pubkey,
        event_id=row.event_id,
        offered_at=row.offered_at,
        status=row.status,
        judgement=dict(row.judgement or {}),
    )


class DjangoOfferStore(OfferStore):
    """``OfferStore`` over ``WorkflowOfferModel``; rows carry ``user_id`` = the owner."""

    def __init__(self, owner_user_id: int | None):
        self.owner_user_id = owner_user_id

    @sync_to_async(thread_sensitive=False)
    def add(self, record: OfferRecord) -> bool:
        if WorkflowOfferModel.objects.filter(content_sha256=record.content_sha256).exists():
            return False
        try:
            with transaction.atomic():
                WorkflowOfferModel.objects.create(
                    content_sha256=record.content_sha256,
                    name=record.name[:255],
                    summary=record.summary,
                    use_when=record.use_when,
                    stats=record.stats,
                    publisher_pubkey=record.publisher_pubkey,
                    event_id=record.event_id,
                    offered_at=record.offered_at,
                    status=record.status,
                    judgement=record.judgement,
                    user_id=self.owner_user_id,
                )
        except IntegrityError:  # stored by another process meanwhile
            return False
        return True

    @sync_to_async(thread_sensitive=False)
    def get(self, content_sha256: str) -> OfferRecord | None:
        row = WorkflowOfferModel.objects.filter(content_sha256=content_sha256).first()
        return _record(row) if row is not None else None

    @sync_to_async(thread_sensitive=False)
    def list(self) -> list[OfferRecord]:
        return [_record(r) for r in WorkflowOfferModel.objects.order_by("-offered_at", "-id")]

    @sync_to_async(thread_sensitive=False)
    def set_status(
        self, content_sha256: str, status: str, judgement: dict[str, Any] | None = None
    ) -> OfferRecord:
        with transaction.atomic():
            row = (
                WorkflowOfferModel.objects.select_for_update()
                .filter(content_sha256=content_sha256)
                .first()
            )
            if row is None:
                raise KeyError(content_sha256)
            check_transition(row.status, status)
            row.status = status
            fields = ["status", "updated_at"]
            if judgement is not None:
                row.judgement = dict(judgement)
                fields.append("judgement")
            row.save(update_fields=fields)
        return _record(row)
