"""``CommonsClient`` over a real relay, with an offline queue (#246, S3b-2).

``RelayCommonsClient`` speaks to one relay through a ``RelayTransport`` (``send`` / ``query``;
``nostr.NostrSdkTransport`` in production, a fake in tests). It never trusts the relay: every
fetched event is re-verified and re-filtered. While the relay is unreachable, publishes go to
an on-disk ``Outbox`` and ``flush()`` resends them in order, so an outage loses nothing.
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zebra_agent.commons.client import CommonsClient, Filter, PublishRefused, _matches_any
from zebra_agent.commons.events import Event, verify_event

logger = logging.getLogger(__name__)

# NIP-01 machine-readable prefixes of an ``OK false`` / ``CLOSED`` message.
PERMANENT_PREFIXES = ("blocked:", "invalid:", "restricted:", "pow:", "mute:")
TRANSIENT_PREFIXES = ("auth-required:", "rate-limited:", "error:", "duplicate:")


class RelayUnavailable(ConnectionError):
    """The relay could not be reached (or did not answer in time)."""


@dataclass(frozen=True)
class SendResult:
    """The relay's answer to one event: stored, or refused with its message."""

    ok: bool
    message: str = ""

    @property
    def permanent(self) -> bool:
        """True when resending the same event will be refused again."""
        return not self.ok and self.message.startswith(PERMANENT_PREFIXES)

    @staticmethod
    def is_relay_answer(message: str) -> bool:
        """Whether *message* came from the relay (vs. a timeout or connection error)."""
        return message.startswith(PERMANENT_PREFIXES + TRANSIENT_PREFIXES)


class RelayTransport(ABC):
    """One relay connection. Both methods raise ``RelayUnavailable`` when it is unreachable."""

    url: str = ""

    @abstractmethod
    async def send(self, event: dict[str, Any]) -> SendResult:
        """Send one event (JSON form)."""

    @abstractmethod
    async def query(self, filters: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Stored events matching the NIP-01 *filters* (JSON form)."""

    async def close(self) -> None:  # noqa: B027 - optional hook
        """Release the connection."""


class Outbox:
    """Events waiting for the relay, oldest first, in a JSONL file (one event per line).

    Refused events are moved to ``<name>.rejected.jsonl`` with the relay's reason. Writes take
    an exclusive ``flock`` (the web and daemon processes share one outbox on the library
    volume).
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.rejected_path = self.path.with_suffix(".rejected.jsonl")
        self._lock_path = self.path.with_suffix(".lock")

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock_path.open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def __repr__(self) -> str:
        return f"Outbox({str(self.path)!r})"

    def events(self) -> list[Event]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                out.append(Event.from_dict(json.loads(line)))
            except ValueError as e:
                logger.error("Sync outbox: dropping an unreadable line: %s", e)
        return out

    def __len__(self) -> int:
        return len(self.events())

    def append(self, event: Event) -> None:
        with self._locked():
            if any(e.id == event.id for e in self.events()):
                return
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
                fh.flush()
                os.fsync(fh.fileno())

    def _write(self, events: list[Event]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            "".join(json.dumps(e.to_dict(), ensure_ascii=False) + "\n" for e in events),
            encoding="utf-8",
        )
        os.replace(tmp, self.path)

    def remove(self, event_ids: set[str]) -> None:
        if event_ids:
            with self._locked():
                self._write([e for e in self.events() if e.id not in event_ids])

    def reject(self, event: Event, reason: str) -> None:
        with self._locked(), self.rejected_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"reason": reason, "event": event.to_dict()}) + "\n")


class RelayCommonsClient(CommonsClient):
    """The private sync relay over a ``RelayTransport``, with an optional ``Outbox``.

    ``publish`` raises ``PublishRefused`` for the hard filter or a permanent refusal by the
    relay; an unreachable relay queues the event (with an outbox) or raises
    ``RelayUnavailable`` (without one).
    """

    def __init__(
        self,
        transport: RelayTransport,
        *,
        outbox: Outbox | None = None,
        private: bool = True,
        poll_interval: float = 5.0,
    ):
        self.transport = transport
        self.outbox = outbox
        self._private = private
        self.poll_interval = poll_interval

    def __repr__(self) -> str:
        return f"RelayCommonsClient({getattr(self.transport, 'url', '')!r})"

    @property
    def private(self) -> bool:
        return self._private

    async def publish(self, event: Event) -> None:
        self.check_publish(event)
        if self.outbox is not None and len(self.outbox):
            self.outbox.append(event)  # keep the order: behind what is already queued
            await self.flush()
            return
        try:
            result = await self.transport.send(event.to_dict())
        except RelayUnavailable as e:
            if self.outbox is None:
                raise
            logger.warning("Sync relay unreachable (%s): queued %s", e, event.id[:12])
            self.outbox.append(event)
            return
        if result.ok:
            return
        if result.permanent or self.outbox is None:
            raise PublishRefused(f"the relay refused the event: {result.message}")
        logger.warning("Sync relay deferred %s (%s): queued", event.id[:12], result.message)
        self.outbox.append(event)

    async def flush(self) -> int:
        """Resend queued events in order; returns how many were delivered (or refused).

        Stops at the first one the relay cannot take now. A permanently refused event moves
        to the rejected file and is logged as an error.
        """
        if self.outbox is None:
            return 0
        done: set[str] = set()
        try:
            for event in self.outbox.events():
                try:
                    result = await self.transport.send(event.to_dict())
                except RelayUnavailable as e:
                    logger.info("Sync relay still unreachable (%s): %d queued", e, len(self.outbox))
                    break
                if result.ok:
                    done.add(event.id)
                elif result.permanent:
                    logger.error("Sync relay refused queued %s: %s", event.id[:12], result.message)
                    self.outbox.reject(event, result.message)
                    done.add(event.id)
                else:
                    break
        finally:
            self.outbox.remove(done)
        return len(done)

    async def fetch(self, filters: list[Filter]) -> list[Event]:
        raw = await self.transport.query([f.to_nostr() for f in filters] or [{}])
        out: dict[str, Event] = {}
        for data in raw:
            try:
                event = Event.from_dict(data)
            except ValueError:
                continue
            if verify_event(event) and _matches_any(filters, event):
                out[event.id] = event
        return sorted(out.values(), key=lambda e: (e.created_at, e.id))

    async def subscribe(self, filters: list[Filter]) -> AsyncIterator[Event]:
        """Stored events, then new ones, by polling ``fetch`` every ``poll_interval``."""
        seen: set[str] = set()
        while True:
            try:
                events = await self.fetch(filters)
            except RelayUnavailable as e:
                logger.info("Sync relay unreachable while subscribed: %s", e)
                events = []
            for event in events:
                if event.id not in seen:
                    seen.add(event.id)
                    yield event
            await asyncio.sleep(self.poll_interval)

    async def close(self) -> None:
        await self.transport.close()
