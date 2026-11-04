"""``SKILL`` events: one workflow sent between devices of the same Zebra (#236, S3b-1).

A ``SKILL`` event is built once per recipient device: the certified, unrevoked devices of
the spheres in the workflow's ``share_with``, never the sender itself. It is signed by the
sending device and ``p``-tagged to its recipient. Content (JSON):

``{name, yaml, commons, stats, sending_device: {pubkey, label, sphere}, chain: [cert]}``

``yaml`` is the relabelled workflow (no ``commons`` block, no local tags), so its hash is
the block's ``content_sha256``. ``stats`` is a snapshot for display only.

Until #246 the content is plaintext (tag ``["enc", "none"]``); #246 swaps in NIP-44
ciphertext to the same recipient, so who can read a copy does not change.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import yaml

from zebra_agent.commons import keys
from zebra_agent.commons.client import SKILL_KIND
from zebra_agent.commons.events import COMMONS_TAG, PROTOCOL_VERSION_TAG, Event, sign_event
from zebra_agent.commons.identity import (
    DEVICE_CERT_KIND,
    DEVICE_REVOKE_KIND,
    DeviceCert,
    verify_attributed,
    verify_device_chain,
)
from zebra_agent.provenance import NotHashableError, content_sha256, read_commons, relabel

ENCRYPTION_TAG = ["enc", "none"]  # S3b-1 placeholder; NIP-44 in #246


class SkillRefused(ValueError):
    """A ``SKILL`` event may not be built for this workflow; the message says why."""


@dataclass
class SkillVerification:
    """The outcome of ``verify_skill``; ``reason`` is ``ok`` when accepted."""

    ok: bool
    reason: str
    name: str | None = None
    yaml: str | None = None
    commons: dict[str, Any] | None = None
    stats: dict[str, Any] = field(default_factory=dict)
    content_sha256: str | None = None
    sender_pubkey: str | None = None
    sender_sphere: str | None = None
    sender_label: str | None = None
    event_id: str | None = None


def skill_payload(yaml_content: str) -> str:
    """The exact workflow text a ``SKILL`` carries: no block, no local tags."""
    return relabel(yaml_content)


def skill_recipients(
    share_with: list[str],
    devices: list[DeviceCert],
    held_events: list[Event],
    *,
    zebra_pubkey: str,
    sender_pubkey: str,
    now: int | None = None,
) -> list[DeviceCert]:
    """The devices a workflow shared with *share_with* is sent to.

    Only certs of this Zebra whose chain still verifies (unexpired, unrevoked) and whose
    sphere is listed; never the sender. ``public`` in ``share_with`` names no device.
    """
    spheres = {s for s in share_with if isinstance(s, str) and s != "public"}
    found: dict[str, DeviceCert] = {}
    for cert in devices:
        if cert.device_pubkey == sender_pubkey or cert.zebra_pubkey != zebra_pubkey:
            continue
        check = verify_device_chain(cert.device_pubkey, zebra_pubkey, held_events, now=now)
        if check.ok and check.cert is not None and check.cert.sphere in spheres:
            found[cert.device_pubkey] = check.cert
    return list(found.values())


def build_skill_events(
    yaml_content: str,
    *,
    device_secret: str,
    zebra_pubkey: str,
    own_cert: Event,
    recipients: list[DeviceCert],
    stats: dict[str, Any] | None = None,
    sending_device: dict[str, Any] | None = None,
    created_at: int | None = None,
) -> list[Event]:
    """One signed ``SKILL`` event per recipient for a library workflow (file text).

    Raises:
        SkillRefused: No block, ``foreign_users``, a hash mismatch, or a recipient
            whose sphere is not in the block's ``share_with``.
    """
    block = read_commons(yaml_content)
    if block is None:
        raise SkillRefused("workflow has no commons block")
    if block.get("foreign_users") is not False:
        raise SkillRefused("workflow saw other users' runs (foreign_users)")
    try:
        body = skill_payload(yaml_content)
        actual = content_sha256(body)
    except NotHashableError as e:
        raise SkillRefused(f"workflow is not hashable: {e}") from e
    if block.get("content_sha256") != actual:
        raise SkillRefused("commons block hash does not match the workflow content")
    share_with = [s for s in block.get("share_with") or [] if isinstance(s, str)]
    device_pubkey = keys.public_key(device_secret)
    name = read_name(body) or "untitled"
    events = []
    for cert in recipients:
        if cert.sphere not in share_with:
            raise SkillRefused(f"sphere {cert.sphere!r} is not in share_with")
        content = json.dumps(
            {
                "name": name,
                "yaml": body,
                "commons": block,
                "stats": stats or {},
                "sending_device": {"pubkey": device_pubkey, **(sending_device or {})},
                "chain": [own_cert.to_dict()],
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        tags = [
            ["p", cert.device_pubkey],
            ["x", actual],
            ["zebra", zebra_pubkey],
            ENCRYPTION_TAG,
            COMMONS_TAG,
            PROTOCOL_VERSION_TAG,
        ]
        events.append(sign_event(device_secret, SKILL_KIND, tags, content, created_at))
    return events


def read_name(yaml_body: str) -> str | None:
    """The workflow's ``name``, or None."""
    try:
        data = yaml.safe_load(yaml_body)
    except yaml.YAMLError:
        return None
    return str(data["name"]) if isinstance(data, dict) and data.get("name") else None


def verify_skill(
    event: Event,
    *,
    device_pubkey: str,
    zebra_pubkey: str,
    sphere: str,
    held_events: list[Event] | None = None,
    now: int | None = None,
) -> SkillVerification:
    """Check a received ``SKILL`` event before anything else looks at it.

    Accepted only when it is a ``SKILL`` addressed to *device_pubkey*, signed by a device
    certified by this device's own Zebra (*zebra_pubkey*) and not revoked (the chain in the
    event plus the certs and revokes this device holds), the YAML hashes to the block's
    ``content_sha256`` and the ``x`` tag, the block is not ``foreign_users`` and this
    device's *sphere* is in the sent ``share_with``. The sender's sphere is read from its
    cert, never from the event body.

    Reasons: ``ok``, ``wrong_kind``, ``not_addressed``, ``wrong_zebra``, ``bad_signature``,
    ``revoked``, ``no_cert``, ``bad_cert``, ``expired``, ``malformed``, ``hash_mismatch``,
    ``not_hashable``, ``foreign_users``, ``not_shared_with_sphere``.
    """
    now = int(time.time()) if now is None else now
    if event.kind != SKILL_KIND:
        return SkillVerification(False, "wrong_kind")
    if event.tag_values("p") != [device_pubkey]:
        return SkillVerification(False, "not_addressed")
    if event.tag_values("zebra") != [zebra_pubkey]:
        return SkillVerification(False, "wrong_zebra")
    content = event.json_content()
    if content is None:
        return SkillVerification(False, "malformed")
    try:
        chain = [Event.from_dict(e) for e in content.get("chain") or []]
    except (ValueError, TypeError):
        return SkillVerification(False, "malformed")
    held = [e for e in held_events or [] if e.kind in (DEVICE_CERT_KIND, DEVICE_REVOKE_KIND)]
    try:
        attributed = verify_attributed(event, zebra_pubkey, chain + held, now=now)
    except (ValueError, TypeError):
        return SkillVerification(False, "bad_signature")
    if not attributed.ok:
        return SkillVerification(False, attributed.reason, sender_pubkey=event.pubkey)
    cert = attributed.cert
    if cert is None:  # signed by the Zebra key itself: sync comes only from devices
        return SkillVerification(False, "no_cert", sender_pubkey=event.pubkey)
    body, block, name = content.get("yaml"), content.get("commons"), content.get("name")
    if not isinstance(body, str) or not isinstance(block, dict) or not isinstance(name, str):
        return SkillVerification(False, "malformed")
    try:
        actual = content_sha256(body)
    except NotHashableError:
        return SkillVerification(False, "not_hashable")
    if not (event.tag_values("x") == [actual] and block.get("content_sha256") == actual):
        return SkillVerification(False, "hash_mismatch")
    if block.get("foreign_users") is not False:
        return SkillVerification(False, "foreign_users")
    if sphere not in (block.get("share_with") or []):
        return SkillVerification(False, "not_shared_with_sphere")
    stats = content.get("stats")
    return SkillVerification(
        True,
        "ok",
        name=name,
        yaml=body,
        commons=block,
        stats=stats if isinstance(stats, dict) else {},
        content_sha256=actual,
        sender_pubkey=event.pubkey,
        sender_sphere=cert.sphere,
        sender_label=cert.label,
        event_id=event.id,
    )
