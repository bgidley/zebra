"""Zebra identity: device certificates, revocations, pairing codes and chain verification.

One Zebra (the Zebra key) runs on several devices (deployments), each with its own device
key. The Zebra key signs a ``DEVICE_CERT`` per device and a ``DEVICE_REVOKE`` for a lost
or retired one. Readers accept an event when its signer has a valid, unexpired, unrevoked
cert chain to the Zebra key (S1, #228).

Revocation order: with no relay, a revoked device's events are rejected outright (S1). With
verified relay receipts (#246), an event from a revoked device is accepted only if its receipt
shows it was stored before the revoke's.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from zebra_agent.commons import keys
from zebra_agent.commons.events import (
    COMMONS_TAG,
    PROTOCOL_VERSION_TAG,
    Event,
    sign_event,
    verify_event,
)
from zebra_agent.commons.kinds import DEVICE_CERT_KIND, DEVICE_REVOKE_KIND

CERT_CODE_PREFIX = "zcert1"
MAX_LABEL_LENGTH = 100
MAX_SPHERE_LENGTH = 40
DEFAULT_SPHERES = ("home", "work")


@dataclass(frozen=True)
class DeviceCert:
    """The parsed content of a ``DEVICE_CERT``."""

    device_pubkey: str
    zebra_pubkey: str
    label: str
    sphere: str
    observed: bool
    expires_at: int | None
    created_at: int
    event: Event


@dataclass(frozen=True)
class ChainResult:
    """Outcome of a cert-chain check. ``reason`` is ``ok`` when accepted."""

    ok: bool
    reason: str
    cert: DeviceCert | None = None


def normalise_sphere(sphere: str) -> str:
    """Lowercase, trimmed sphere name; raises ``ValueError`` if empty or too long."""
    value = (sphere or "").strip().lower()
    if not value:
        raise ValueError("sphere is required")
    if len(value) > MAX_SPHERE_LENGTH:
        raise ValueError(f"sphere must be at most {MAX_SPHERE_LENGTH} characters")
    return value


def _clean_label(label: str) -> str:
    value = (label or "").strip()
    if not value:
        raise ValueError("label is required")
    if len(value) > MAX_LABEL_LENGTH:
        raise ValueError(f"label must be at most {MAX_LABEL_LENGTH} characters")
    return value


def make_device_cert(
    zebra_secret: str,
    device_pubkey: str,
    *,
    label: str,
    sphere: str,
    observed: bool,
    expires_at: int | None = None,
    created_at: int | None = None,
) -> Event:
    """Sign a ``DEVICE_CERT``: "device key D belongs to this Zebra"."""
    if not keys.is_valid_public_key(device_pubkey):
        raise ValueError("device public key is not valid")
    content: dict[str, Any] = {
        "label": _clean_label(label),
        "sphere": normalise_sphere(sphere),
        "observed": bool(observed),
    }
    if expires_at is not None:
        content["expires_at"] = int(expires_at)
    tags = [["d", device_pubkey], ["p", device_pubkey], COMMONS_TAG, PROTOCOL_VERSION_TAG]
    return sign_event(
        zebra_secret,
        DEVICE_CERT_KIND,
        tags,
        json.dumps(content, sort_keys=True, separators=(",", ":")),
        created_at,
    )


def make_device_revoke(
    zebra_secret: str,
    device_pubkey: str,
    *,
    reason: str = "",
    created_at: int | None = None,
) -> Event:
    """Sign a ``DEVICE_REVOKE`` for a lost or retired device."""
    if not keys.is_valid_public_key(device_pubkey):
        raise ValueError("device public key is not valid")
    tags = [["p", device_pubkey], COMMONS_TAG, PROTOCOL_VERSION_TAG]
    content = json.dumps({"reason": (reason or "").strip()[:500]}, separators=(",", ":"))
    return sign_event(zebra_secret, DEVICE_REVOKE_KIND, tags, content, created_at)


def parse_cert(event: Event) -> DeviceCert | None:
    """Parse a ``DEVICE_CERT`` event's content; None if it is not a well-formed cert.

    Does not check the signature: use ``verify_device_chain`` for that.
    """
    if event.kind != DEVICE_CERT_KIND:
        return None
    d_values = event.tag_values("d")
    p_values = event.tag_values("p")
    if len(d_values) != 1 or p_values != d_values:
        return None
    content = event.json_content()
    if content is None:
        return None
    label = content.get("label")
    sphere = content.get("sphere")
    observed = content.get("observed")
    expires_at = content.get("expires_at")
    if not isinstance(label, str) or not isinstance(sphere, str) or not isinstance(observed, bool):
        return None
    if expires_at is not None and (isinstance(expires_at, bool) or not isinstance(expires_at, int)):
        return None
    return DeviceCert(
        device_pubkey=d_values[0],
        zebra_pubkey=event.pubkey,
        label=label,
        sphere=sphere,
        observed=observed,
        expires_at=expires_at,
        created_at=event.created_at,
        event=event,
    )


def revoked_by_order(
    revokes: list[Event], event_id: str | None, receipt_seq: Mapping[str, int] | None
) -> str | None:
    """Why the revokes in *revokes* reject the event *event_id*, or None if they do not.

    No receipts (or no event id): any revoke rejects (``revoked``, the S1 rule). With
    receipts: the event needs a receipt (``no_receipt``) whose ``seq`` precedes the receipt of
    every revoke; a revoke with no receipt still rejects.
    """
    if not revokes:
        return None
    if receipt_seq is None or event_id is None:
        return "revoked"
    seq = receipt_seq.get(event_id)
    if seq is None:
        return "no_receipt"
    revoke_seqs = [receipt_seq.get(r.id) for r in revokes]
    if any(s is None for s in revoke_seqs) or seq >= min(revoke_seqs):
        return "revoked"
    return None


def verify_device_chain(
    device_pubkey: str,
    zebra_pubkey: str,
    events: list[Event],
    *,
    now: int | None = None,
    receipt_seq: Mapping[str, int] | None = None,
    event_id: str | None = None,
) -> ChainResult:
    """Check that ``device_pubkey`` holds a valid, unexpired, unrevoked cert from ``zebra_pubkey``.

    ``events`` is every cert and revoke the reader knows of; others are ignored, as are
    events with a bad id or signature or signed by any key but the Zebra key.

    ``receipt_seq`` (event id → relay receipt ``seq``, from verified receipts) and
    ``event_id`` judge one event of the device by receipt order (``revoked_by_order``).
    Without them a revoke rejects the device outright: use that for "may I send to it now".

    Reasons: ``ok``, ``revoked``, ``no_receipt``, ``no_cert``, ``bad_cert``, ``expired``.
    """
    now = int(time.time()) if now is None else now
    trusted = [
        e
        for e in events
        if e.pubkey == zebra_pubkey
        and e.kind in (DEVICE_CERT_KIND, DEVICE_REVOKE_KIND)
        and verify_event(e)
    ]
    revokes = [
        e for e in trusted if e.kind == DEVICE_REVOKE_KIND and device_pubkey in e.tag_values("p")
    ]
    reason = revoked_by_order(revokes, event_id, receipt_seq)
    if reason is not None:
        return ChainResult(False, reason)
    certs = [
        e for e in trusted if e.kind == DEVICE_CERT_KIND and e.tag_values("d") == [device_pubkey]
    ]
    if not certs:
        return ChainResult(False, "no_cert")
    latest = max(certs, key=lambda e: (e.created_at, e.id))
    cert = parse_cert(latest)
    if cert is None:
        return ChainResult(False, "bad_cert")
    if cert.expires_at is not None and cert.expires_at <= now:
        return ChainResult(False, "expired", cert)
    return ChainResult(True, "ok", cert)


def verify_attributed(
    event: Event,
    zebra_pubkey: str,
    chain_events: list[Event],
    *,
    now: int | None = None,
    receipt_seq: Mapping[str, int] | None = None,
) -> ChainResult:
    """Accept ``event`` as coming from the Zebra ``zebra_pubkey``.

    It must carry a valid signature, and be signed either by the Zebra key itself or by a
    device key with a valid chain (``verify_device_chain``, judged by receipt order when
    *receipt_seq* is given). Reason ``bad_signature`` when its own signature fails.
    """
    if not verify_event(event):
        return ChainResult(False, "bad_signature")
    if event.pubkey == zebra_pubkey:
        return ChainResult(True, "ok")
    return verify_device_chain(
        event.pubkey,
        zebra_pubkey,
        chain_events,
        now=now,
        receipt_seq=receipt_seq,
        event_id=event.id,
    )


# ---------------------------------------------------------------------------
# Pairing: codes the human carries between devices
# ---------------------------------------------------------------------------


def pairing_code(device_pubkey: str) -> str:
    """The code a new device shows to be paired: its device ``npub``."""
    return keys.npub_encode(device_pubkey)


def parse_pairing_code(code: str) -> str:
    """Device pubkey (hex) from a pairing code; raises ``ValueError`` if invalid."""
    return keys.npub_decode((code or "").strip())


def fingerprint(pubkey: str) -> str:
    """Short ``XXXX-XXXX`` fingerprint of a public key, compared by eye on both devices."""
    digest = hashlib.sha256(bytes.fromhex(pubkey)).digest()
    text = base64.b32encode(digest).decode("ascii")[:8]
    return f"{text[:4]}-{text[4:]}"


def encode_cert_code(event: Event) -> str:
    """Pack a cert event into a copy-paste code (``zcert1`` + base64url JSON)."""
    raw = json.dumps(event.to_dict(), separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return CERT_CODE_PREFIX + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cert_code(code: str) -> Event:
    """Unpack a cert code; raises ``ValueError`` if it is not one."""
    text = "".join((code or "").split())
    if not text.startswith(CERT_CODE_PREFIX):
        raise ValueError("not a certificate code")
    body = text[len(CERT_CODE_PREFIX) :]
    try:
        raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        data = json.loads(raw.decode("utf-8"))
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise ValueError("certificate code is corrupted") from exc
    return Event.from_dict(data)
