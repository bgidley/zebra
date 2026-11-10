"""The local mirror of Commons events (#231, S4).

Every Commons event this Zebra publishes or relies on (its ``OFFER``s, the certs it put on a
public relay, the ``RECEIPT``s that order them) is kept once, append-only: a row is never
changed or deleted. ``CommonsMirror`` is the interface; ``InMemoryCommonsMirror`` serves tests
and the CLI, the web app's ``DjangoCommonsMirror`` stores rows in ``CommonsEventModel``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from zebra_agent.commons.events import Event
from zebra_agent.commons.kinds import OFFER_KIND, RECEIPT_KIND


@dataclass(frozen=True)
class MirroredEvent:
    """One stored event; ``relay_seq`` is the canonical relay's receipt ``seq`` if known."""

    event: Event
    relay_seq: int | None = None


class CommonsMirror(ABC):
    """Append-only store of Commons events."""

    @abstractmethod
    async def add(self, event: Event, *, relay_seq: int | None = None) -> bool:
        """Store *event* once; False (and nothing changed) if it is already stored."""

    @abstractmethod
    async def get(self, event_id: str) -> MirroredEvent | None:
        """The stored event with this id, or None."""

    @abstractmethod
    async def events(
        self, *, kind: int | None = None, pubkey: str | None = None
    ) -> list[MirroredEvent]:
        """Stored events (optionally of one kind / author), oldest first."""

    async def offered_hashes(self, zebra_pubkey: str) -> set[str]:
        """Content hashes this Zebra has published an ``OFFER`` of."""
        return {
            d
            for m in await self.events(kind=OFFER_KIND)
            if m.event.tag_values("zebra") == [zebra_pubkey]
            for d in m.event.tag_values("d")
        }

    async def public_hashes(self) -> set[str]:
        """Content hashes publicly offered by any Zebra: an ``OFFER`` of each is held here.

        The mirror holds only this Zebra's own events and events it verified at intake, so
        every hash here is public. ``public_parent`` names a parent only from this set.
        """
        return {d for m in await self.events(kind=OFFER_KIND) for d in m.event.tag_values("d")}

    async def receipt_seq(self, operator_pubkey: str) -> dict[str, int]:
        """Event id → ``seq`` from the stored receipts of *operator_pubkey*."""
        from zebra_agent.commons.receipts import receipt_order

        rows = await self.events(kind=RECEIPT_KIND, pubkey=operator_pubkey)
        return receipt_order([m.event for m in rows], operator_pubkey)


class InMemoryCommonsMirror(CommonsMirror):
    """``CommonsMirror`` in a list (tests, CLI)."""

    def __init__(self) -> None:
        self._rows: list[MirroredEvent] = []

    async def add(self, event: Event, *, relay_seq: int | None = None) -> bool:
        if any(m.event.id == event.id for m in self._rows):
            return False
        self._rows.append(MirroredEvent(event, relay_seq))
        return True

    async def get(self, event_id: str) -> MirroredEvent | None:
        return next((m for m in self._rows if m.event.id == event_id), None)

    async def events(
        self, *, kind: int | None = None, pubkey: str | None = None
    ) -> list[MirroredEvent]:
        return [
            m
            for m in self._rows
            if (kind is None or m.event.kind == kind)
            and (pubkey is None or m.event.pubkey == pubkey)
        ]
