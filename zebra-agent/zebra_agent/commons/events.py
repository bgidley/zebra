"""NIP-01 Nostr events: canonical id, BIP-340 signature, verification.

Commons events are standard Nostr events so the relay slice (#246) can publish them
unchanged. ``Event`` is immutable and JSON-serialisable via ``to_dict()``.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

from zebra_agent.commons import keys

COMMONS_TAG = ["t", "zebra-commons"]
PROTOCOL_VERSION_TAG = ["v", "1"]


@dataclass(frozen=True)
class Event:
    """A signed NIP-01 event."""

    id: str
    pubkey: str
    created_at: int
    kind: int
    tags: list[list[str]] = field(default_factory=list)
    content: str = ""
    sig: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "pubkey": self.pubkey,
            "created_at": self.created_at,
            "kind": self.kind,
            "tags": [list(t) for t in self.tags],
            "content": self.content,
            "sig": self.sig,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Event:
        """Build an event from its JSON form; raises ``ValueError`` if malformed."""
        if not isinstance(data, dict):
            raise ValueError("event must be an object")
        try:
            tags = data.get("tags") or []
            if not isinstance(tags, list) or not all(
                isinstance(t, list) and all(isinstance(x, str) for x in t) for t in tags
            ):
                raise ValueError("tags must be a list of string lists")
            return cls(
                id=str(data["id"]),
                pubkey=str(data["pubkey"]),
                created_at=int(data["created_at"]),
                kind=int(data["kind"]),
                tags=[list(t) for t in tags],
                content=str(data.get("content", "")),
                sig=str(data["sig"]),
            )
        except (KeyError, TypeError) as exc:
            raise ValueError(f"malformed event: {exc}") from exc

    def tag_values(self, name: str) -> list[str]:
        """Values of every tag called ``name`` (first element after the name)."""
        return [t[1] for t in self.tags if len(t) >= 2 and t[0] == name]

    def json_content(self) -> dict[str, Any] | None:
        """The content parsed as a JSON object, or None."""
        try:
            value = json.loads(self.content)
        except (ValueError, TypeError):
            return None
        return value if isinstance(value, dict) else None


def event_id(pubkey: str, created_at: int, kind: int, tags: list[list[str]], content: str) -> str:
    """NIP-01 id: sha256 of ``[0, pubkey, created_at, kind, tags, content]``."""
    serialized = json.dumps(
        [0, pubkey, created_at, kind, tags, content],
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def sign_event(
    secret_hex: str,
    kind: int,
    tags: list[list[str]],
    content: str,
    created_at: int | None = None,
) -> Event:
    """Build and sign an event with ``secret_hex``."""
    pubkey = keys.public_key(secret_hex)
    created = int(time.time()) if created_at is None else int(created_at)
    tags = [list(t) for t in tags]
    eid = event_id(pubkey, created, kind, tags, content)
    sig = keys.sign(secret_hex, bytes.fromhex(eid))
    return Event(
        id=eid, pubkey=pubkey, created_at=created, kind=kind, tags=tags, content=content, sig=sig
    )


def verify_event(event: Event) -> bool:
    """True when the id matches the content and the signature is valid for ``pubkey``."""
    try:
        expected = event_id(event.pubkey, event.created_at, event.kind, event.tags, event.content)
    except (TypeError, ValueError):
        return False
    if expected != event.id:
        return False
    return keys.verify(event.pubkey, bytes.fromhex(event.id), event.sig)
