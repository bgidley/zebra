"""Offers this Zebra has seen on the public Commons, one per content hash (#232, S5).

``OfferStore`` is the interface; ``InMemoryOfferStore`` serves tests and the CLI, the web app's
``DjangoOfferStore`` stores rows in ``WorkflowOfferModel``. Status changes follow one fixed
table (``TRANSITIONS``); anything else raises ``InvalidOfferTransition``.
"""

from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from typing import Any

SEEN = "seen"
JUDGING = "judging"
ADOPTED = "adopted"
REJECTED = "rejected"
DELISTED = "delisted"
STATUSES = (SEEN, JUDGING, ADOPTED, REJECTED, DELISTED)

TRANSITIONS: dict[str, frozenset[str]] = {
    SEEN: frozenset({JUDGING, DELISTED}),
    # back to seen when the import could not run at all
    JUDGING: frozenset({ADOPTED, REJECTED, SEEN, DELISTED}),
    REJECTED: frozenset({JUDGING, DELISTED}),
    ADOPTED: frozenset({DELISTED}),
    DELISTED: frozenset(),
}
#: Statuses from which the owner may start a judged import.
IMPORTABLE = frozenset({SEEN, REJECTED})


class InvalidOfferTransition(ValueError):
    """A status change the table does not allow."""


def check_transition(current: str, new: str) -> None:
    """Raise ``InvalidOfferTransition`` unless *current* → *new* is allowed."""
    if new not in TRANSITIONS.get(current, frozenset()):
        raise InvalidOfferTransition(f"an offer cannot go from {current} to {new}")


@dataclass(frozen=True)
class OfferRecord:
    """One offer seen on the Commons.

    Attributes:
        content_sha256: The workflow's content hash (unique)
        name / summary / use_when / stats: From the ``OFFER`` content
        publisher_pubkey: The publishing Zebra's key
        event_id: The ``OFFER`` event (in the local mirror)
        offered_at: The ``OFFER``'s ``created_at``
        status: ``seen`` / ``judging`` / ``adopted`` / ``rejected`` / ``delisted``
        judgement: This Zebra's verdict, local only (stage, label, reason, process id)
    """

    content_sha256: str
    name: str
    publisher_pubkey: str
    event_id: str
    summary: str = ""
    use_when: str = ""
    stats: dict[str, Any] = field(default_factory=dict)
    offered_at: int = 0
    status: str = SEEN
    judgement: dict[str, Any] = field(default_factory=dict)


class OfferStore(ABC):
    """Offers seen, keyed by content hash."""

    @abstractmethod
    async def add(self, record: OfferRecord) -> bool:
        """Store *record*; False (nothing changed) if its hash is already stored."""

    @abstractmethod
    async def get(self, content_sha256: str) -> OfferRecord | None:
        """The offer with this hash, or None."""

    @abstractmethod
    async def list(self) -> list[OfferRecord]:
        """Every stored offer, newest offer first."""

    @abstractmethod
    async def set_status(
        self, content_sha256: str, status: str, judgement: dict[str, Any] | None = None
    ) -> OfferRecord:
        """Move an offer to *status* (and replace its judgement when given).

        Raises:
            KeyError: No offer with that hash.
            InvalidOfferTransition: The table does not allow it.
        """


class InMemoryOfferStore(OfferStore):
    """``OfferStore`` in a dict (tests, CLI)."""

    def __init__(self) -> None:
        self._rows: dict[str, OfferRecord] = {}

    async def add(self, record: OfferRecord) -> bool:
        if record.content_sha256 in self._rows:
            return False
        self._rows[record.content_sha256] = copy.deepcopy(record)
        return True

    async def get(self, content_sha256: str) -> OfferRecord | None:
        return self._rows.get(content_sha256)

    async def list(self) -> list[OfferRecord]:
        return sorted(self._rows.values(), key=lambda r: r.offered_at, reverse=True)

    async def set_status(
        self, content_sha256: str, status: str, judgement: dict[str, Any] | None = None
    ) -> OfferRecord:
        row = self._rows[content_sha256]
        check_transition(row.status, status)
        row = replace(
            row,
            status=status,
            judgement=dict(judgement) if judgement is not None else row.judgement,
        )
        self._rows[content_sha256] = row
        return row
