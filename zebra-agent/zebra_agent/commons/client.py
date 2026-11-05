"""The Commons transport interface and an in-memory implementation (#236, S3b-1).

Everything outside ``commons/`` talks to relays through ``CommonsClient``: ``publish``,
``subscribe`` and ``fetch``. The Nostr implementation (``nostr-sdk``, private strfry relay,
NIP-44, receipts) is #246; until then ``InMemoryCommonsClient`` over a shared
``InMemoryRelay`` carries events between devices in tests.

The hard filter lives here so no implementation can skip it: a ``SKILL`` event is refused
on any relay that is not private.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from zebra_agent.commons.events import Event, verify_event

# Provisional until #246/S4 fix the kinds (nothing is published outside tests).
SKILL_KIND = 4236


class PublishRefused(ValueError):
    """The client refused to publish an event (hard filter or a bad event)."""


@dataclass(frozen=True)
class Filter:
    """A NIP-01 style subscription filter; empty fields match anything."""

    kinds: tuple[int, ...] = ()
    authors: tuple[str, ...] = ()
    recipients: tuple[str, ...] = ()  # values of ``p`` tags
    since: int | None = None

    def matches(self, event: Event) -> bool:
        if self.kinds and event.kind not in self.kinds:
            return False
        if self.authors and event.pubkey not in self.authors:
            return False
        if self.recipients and not set(event.tag_values("p")) & set(self.recipients):
            return False
        if self.since is not None and event.created_at < self.since:
            return False
        return True


def _matches_any(filters: list[Filter], event: Event) -> bool:
    return any(f.matches(event) for f in filters) if filters else True


class CommonsClient(ABC):
    """A connection to one Commons relay."""

    @property
    @abstractmethod
    def private(self) -> bool:
        """True for the private sync relay (the only place ``SKILL`` events may go)."""

    @abstractmethod
    async def publish(self, event: Event) -> None:
        """Publish a signed event. Raises ``PublishRefused`` if the hard filter refuses it."""

    @abstractmethod
    def subscribe(self, filters: list[Filter]) -> AsyncIterator[Event]:
        """Stored events matching *filters*, then new ones as they arrive."""

    @abstractmethod
    async def fetch(self, filters: list[Filter]) -> list[Event]:
        """Stored events matching *filters*, oldest first."""

    def check_publish(self, event: Event) -> None:
        """The hard filter every implementation applies before sending."""
        if event.kind == SKILL_KIND and not self.private:
            raise PublishRefused("SKILL events may only go to the private sync relay")
        if not verify_event(event):
            raise PublishRefused("event id or signature is invalid")


@dataclass
class InMemoryRelay:
    """A relay held in memory: stores events in arrival order, fans them out."""

    private: bool = True
    events: list[Event] = field(default_factory=list)
    _queues: list[asyncio.Queue] = field(default_factory=list, repr=False)

    def store(self, event: Event) -> None:
        if any(e.id == event.id for e in self.events):
            return
        self.events.append(event)
        for queue in list(self._queues):
            queue.put_nowait(event)


class InMemoryCommonsClient(CommonsClient):
    """``CommonsClient`` over an ``InMemoryRelay`` shared by the devices under test."""

    def __init__(self, relay: InMemoryRelay):
        self.relay = relay

    @property
    def private(self) -> bool:
        return self.relay.private

    async def publish(self, event: Event) -> None:
        self.check_publish(event)
        self.relay.store(event)

    async def fetch(self, filters: list[Filter]) -> list[Event]:
        return [e for e in self.relay.events if _matches_any(filters, e)]

    async def subscribe(self, filters: list[Filter]) -> AsyncIterator[Event]:
        queue: asyncio.Queue = asyncio.Queue()
        self.relay._queues.append(queue)
        try:
            for event in list(self.relay.events):
                if _matches_any(filters, event):
                    yield event
            while True:
                event = await queue.get()
                if _matches_any(filters, event):
                    yield event
        finally:
            self.relay._queues.remove(queue)
