"""``DjangoCommonsMirror``: the local mirror of Commons events in ``CommonsEventModel`` (#231).

Append-only, owned by the Commons owner (REQ-USR-002). ORM calls are
``sync_to_async(thread_sensitive=False)`` because ``commons_publish`` runs inside goal tasks
that outlive the request that started them (#123).
"""

from __future__ import annotations

from asgiref.sync import sync_to_async
from django.db import IntegrityError, transaction
from zebra_agent.commons.events import Event
from zebra_agent.commons.mirror import CommonsMirror, MirroredEvent

from zebra_agent_web.api.models import CommonsEventModel


def _row_to_mirrored(row: CommonsEventModel) -> MirroredEvent:
    return MirroredEvent(Event.from_dict(row.event), row.relay_seq)


class DjangoCommonsMirror(CommonsMirror):
    """``CommonsMirror`` over ``CommonsEventModel``; rows carry ``user_id`` = the owner."""

    def __init__(self, owner_user_id: int | None):
        self.owner_user_id = owner_user_id

    @sync_to_async(thread_sensitive=False)
    def add(self, event: Event, *, relay_seq: int | None = None) -> bool:
        if CommonsEventModel.objects.filter(event_id=event.id).exists():
            return False
        content = event.json_content()
        try:
            with transaction.atomic():
                CommonsEventModel.objects.create(
                    event_id=event.id,
                    kind=event.kind,
                    pubkey=event.pubkey,
                    created_at=event.created_at,
                    relay_seq=relay_seq,
                    content=content if content is not None else {"text": event.content},
                    sig=event.sig,
                    event=event.to_dict(),
                    user_id=self.owner_user_id,
                )
        except IntegrityError:  # stored by another process meanwhile
            return False
        return True

    @sync_to_async(thread_sensitive=False)
    def get(self, event_id: str) -> MirroredEvent | None:
        row = CommonsEventModel.objects.filter(event_id=event_id).first()
        return _row_to_mirrored(row) if row is not None else None

    @sync_to_async(thread_sensitive=False)
    def events(self, *, kind: int | None = None, pubkey: str | None = None) -> list[MirroredEvent]:
        rows = CommonsEventModel.objects.all()
        if kind is not None:
            rows = rows.filter(kind=kind)
        if pubkey is not None:
            rows = rows.filter(pubkey=pubkey)
        return [_row_to_mirrored(r) for r in rows.order_by("id")]
