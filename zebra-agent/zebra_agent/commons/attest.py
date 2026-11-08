"""``ATTEST`` events: what happened when a Zebra tried a public offer (#232, S5).

NIP-32 style labels on a workflow's content hash, kind ``ATTEST_KIND``, signed by a certified
device key and attributed to its Zebra through the device's ``DEVICE_CERT``::

    tags    ["L","zebra-commons"], ["l",<label>,"zebra-commons"], ["x",<sha256>],
            ["zebra",<attesting Zebra pubkey>], ["t","zebra-commons"], ["v","1"]
    content {"reason": <fixed vocabulary>, "rating"?: 1-5}

**No personal data, by construction.** Nothing here takes free text: the label and the reason
come from fixed tables, the rating is a small integer and the only other inputs are keys and a
hash. Goal text, outputs, workflow names, people and LLM text cannot reach an attestation, and
``verify_attest`` refuses any event carrying anything else.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass

from zebra_agent.commons import keys
from zebra_agent.commons.events import COMMONS_TAG, PROTOCOL_VERSION_TAG, Event, sign_event
from zebra_agent.commons.identity import verify_attributed, verify_device_chain
from zebra_agent.commons.kinds import ATTEST_KIND

NAMESPACE = "zebra-commons"

ADOPTED = "adopted"
REJECTED_ETHICS = "rejected-ethics"
REJECTED_GYM = "rejected-gym"
REJECTED_PII = "rejected-pii"
PII_FOUND = "pii-found"
WORKED = "worked"
FAILED = "failed"

#: Label → the reasons it may carry (first is the default). Never free text.
REASONS: dict[str, tuple[str, ...]] = {
    ADOPTED: ("passed-checks", "owner-approved"),
    REJECTED_ETHICS: ("ethics-review",),
    REJECTED_GYM: ("golden-tasks-failed",),
    REJECTED_PII: ("scan-failed-closed",),
    PII_FOUND: ("personal-data",),
    WORKED: ("run-succeeded",),
    FAILED: ("run-failed",),
}
LABELS = tuple(REASONS)
#: Labels that say the importer turned the workflow down.
REJECTION_LABELS = frozenset({REJECTED_ETHICS, REJECTED_GYM, REJECTED_PII, PII_FOUND})
_TAG_NAMES = frozenset({"L", "l", "x", "zebra", "t", "v"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class AttestRefused(ValueError):
    """An attestation cannot be built; the message says why."""


@dataclass(frozen=True)
class AttestVerification:
    """The outcome of ``verify_attest``; ``reason`` is ``ok`` when accepted."""

    ok: bool
    reason: str
    zebra_pubkey: str | None = None
    label: str | None = None
    content_sha256: str | None = None
    attest_reason: str | None = None
    rating: int | None = None


def attest_content(label: str, reason: str | None = None, rating: int | None = None) -> str:
    """The canonical content JSON. Raises ``AttestRefused`` for anything off the tables."""
    if label not in REASONS:
        raise AttestRefused(f"unknown attestation label {label!r}")
    reason = reason or REASONS[label][0]
    if reason not in REASONS[label]:
        raise AttestRefused(f"{reason!r} is not a reason for {label}")
    body: dict[str, object] = {"reason": reason}
    if rating is not None:
        if isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 5:
            raise AttestRefused("rating must be an integer 1-5")
        body["rating"] = rating
    return json.dumps(body, sort_keys=True, separators=(",", ":"))


def attest_tags(label: str, content_sha256: str, zebra_pubkey: str) -> list[list[str]]:
    """The fixed tag set of an attestation."""
    return [
        ["L", NAMESPACE],
        ["l", label, NAMESPACE],
        ["x", content_sha256],
        ["zebra", zebra_pubkey],
        COMMONS_TAG,
        PROTOCOL_VERSION_TAG,
    ]


def build_attest(
    label: str,
    content_sha256: str,
    *,
    device_secret: str,
    zebra_pubkey: str,
    chain: list[Event],
    reason: str | None = None,
    rating: int | None = None,
    created_at: int | None = None,
) -> Event:
    """Sign an ``ATTEST`` of *label* on *content_sha256* with the device key.

    Raises:
        AttestRefused: Unknown label or reason, a bad rating or hash, or a device that is not
            attributed to *zebra_pubkey* by a valid cert in *chain*.
    """
    if not isinstance(content_sha256, str) or not _SHA256.match(content_sha256):
        raise AttestRefused("content hash must be 64 lowercase hex characters")
    content = attest_content(label, reason, rating)
    device_pubkey = keys.public_key(device_secret)
    if device_pubkey != zebra_pubkey:
        check = verify_device_chain(device_pubkey, zebra_pubkey, chain, now=created_at)
        if not check.ok:
            raise AttestRefused(f"this device is not attributed to its Zebra ({check.reason})")
    return sign_event(
        device_secret,
        ATTEST_KIND,
        attest_tags(label, content_sha256, zebra_pubkey),
        content,
        created_at,
    )


def verify_attest(
    event: Event,
    chain_events: list[Event],
    *,
    now: int | None = None,
    receipt_seq: Mapping[str, int] | None = None,
) -> AttestVerification:
    """Check an ``ATTEST``: kind, exact tags, content from the tables, attribution.

    Reasons: ``ok``, ``wrong_kind``, ``malformed``, ``bad_reason`` and the attribution reasons
    of ``verify_attributed`` (``bad_signature``, ``no_cert``, ``revoked``, ``expired``, ...).
    """
    if event.kind != ATTEST_KIND:
        return AttestVerification(False, "wrong_kind")
    if any(not t or t[0] not in _TAG_NAMES for t in event.tags) or len(event.tags) != 6:
        return AttestVerification(False, "malformed")
    zebras, xs, labels = event.tag_values("zebra"), event.tag_values("x"), event.tag_values("l")
    if len(zebras) != 1 or len(xs) != 1 or len(labels) != 1:
        return AttestVerification(False, "malformed")
    zebra, sha, label = zebras[0], xs[0], labels[0]
    if label not in REASONS or not _SHA256.match(sha):
        return AttestVerification(False, "malformed", zebra_pubkey=zebra)
    if event.tags != attest_tags(label, sha, zebra):
        return AttestVerification(False, "malformed", zebra_pubkey=zebra)
    content = event.json_content()
    if content is None or not set(content) <= {"reason", "rating"} or "reason" not in content:
        return AttestVerification(False, "malformed", zebra_pubkey=zebra)
    try:
        canonical = attest_content(label, content.get("reason"), content.get("rating"))
    except AttestRefused:
        return AttestVerification(False, "bad_reason", zebra_pubkey=zebra)
    if canonical != event.content:
        return AttestVerification(False, "malformed", zebra_pubkey=zebra)
    attributed = verify_attributed(event, zebra, chain_events, now=now, receipt_seq=receipt_seq)
    if not attributed.ok:
        return AttestVerification(False, attributed.reason, zebra_pubkey=zebra)
    return AttestVerification(
        True,
        "ok",
        zebra_pubkey=zebra,
        label=label,
        content_sha256=sha,
        attest_reason=content["reason"],
        rating=content.get("rating"),
    )
