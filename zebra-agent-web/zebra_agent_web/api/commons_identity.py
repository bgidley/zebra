"""Zebra Commons identity for this deployment (S1, #228).

Glue between the pure ``zebra_agent.commons`` package, the credential store that holds
the secret keys and the database rows that hold public keys, certs and revokes:

- ``SystemStateModel`` (pk=1): this deployment's Zebra pubkey, device pubkey, label,
  sphere, observed flag, sync direction and Commons owner.
- ``CommonsDeviceModel``: one row per device certified by a Zebra key, with the signed
  ``DEVICE_CERT`` and any ``DEVICE_REVOKE``.

Nothing is published (that is #246). Every mutating function assumes the caller has
already checked ``commons_enabled()`` and that the user is the owner.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from zebra_agent.commons import keys
from zebra_agent.commons.events import Event, verify_event
from zebra_agent.commons.identity import (
    decode_cert_code,
    encode_cert_code,
    fingerprint,
    make_device_cert,
    make_device_revoke,
    pairing_code,
    parse_cert,
    parse_pairing_code,
    verify_device_chain,
)
from zebra_agent.commons.keystore import CommonsKeys
from zebra_agent.storage.credentials import FileCredentialStore

from zebra_agent_web.api.models import CommonsDeviceModel, SystemStateModel

logger = logging.getLogger(__name__)

# One device key per deployment: serialise its first creation within this process.
_device_key_lock = asyncio.Lock()


class CommonsError(ValueError):
    """A Commons action was refused; the message is safe to show the owner."""


def commons_enabled() -> bool:
    """The ``COMMONS_ENABLED`` master switch (default off)."""
    return bool(settings.ZEBRA_AGENT_SETTINGS.get("COMMONS_ENABLED", False))


def get_commons_keys() -> CommonsKeys:
    """The keystore over the Commons key directory (``COMMONS_KEY_DIR``)."""
    key_dir = settings.ZEBRA_AGENT_SETTINGS.get("COMMONS_KEY_DIR", "~/.zebra-agent/commons-keys")
    return CommonsKeys(FileCredentialStore(Path(key_dir).expanduser()))


async def _state() -> SystemStateModel:
    obj, _ = await SystemStateModel.objects.aget_or_create(pk=1)
    return obj


async def get_owner_id() -> int | None:
    """The Commons owner's user id, defaulting to (and persisting) the first user."""
    state = await _state()
    if state.commons_owner_user_id is not None:
        return state.commons_owner_user_id
    first = await get_user_model().objects.order_by("id").afirst()
    if first is None:
        return None
    state.commons_owner_user_id = first.id
    await state.asave(update_fields=["commons_owner_user_id"])
    return first.id


async def is_owner(user: Any) -> bool:
    """True when ``user`` is signed in and is the Commons owner."""
    if not getattr(user, "is_authenticated", False):
        return False
    return user.id == await get_owner_id()


async def _ensure_device(state: SystemStateModel, commons_keys: CommonsKeys) -> str:
    """This device's secret key, created on first use; keeps ``state.device_pubkey`` in step."""
    async with _device_key_lock:
        secret = await commons_keys.get_or_create_device_secret()
    pubkey = keys.public_key(secret)
    if state.device_pubkey != pubkey:
        state.device_pubkey = pubkey
        await state.asave(update_fields=["device_pubkey"])
    return secret


def _expires_dt(expires_at: int | None) -> datetime | None:
    return datetime.fromtimestamp(expires_at, UTC) if expires_at is not None else None


async def _store_cert(cert_event: Event, owner_id: int | None) -> CommonsDeviceModel:
    cert = parse_cert(cert_event)
    assert cert is not None  # built or verified by the caller
    row, _ = await CommonsDeviceModel.objects.aupdate_or_create(
        zebra_pubkey=cert.zebra_pubkey,
        device_pubkey=cert.device_pubkey,
        defaults={
            "label": cert.label,
            "sphere": cert.sphere,
            "observed": cert.observed,
            "expires_at": _expires_dt(cert.expires_at),
            "cert_event": cert_event.to_dict(),
            "user_id": owner_id,
        },
    )
    return row


async def _chain_events(zebra_pubkey: str) -> list[Event]:
    events: list[Event] = []
    async for row in CommonsDeviceModel.objects.filter(zebra_pubkey=zebra_pubkey):
        events.append(Event.from_dict(row.cert_event))
        if row.revoke_event:
            events.append(Event.from_dict(row.revoke_event))
    return events


async def _self_certify(
    state: SystemStateModel,
    zebra_secret: str,
    device_secret: str,
    *,
    label: str,
    sphere: str,
    observed: bool,
) -> None:
    device_pubkey = keys.public_key(device_secret)
    try:
        cert_event = make_device_cert(
            zebra_secret, device_pubkey, label=label, sphere=sphere, observed=observed
        )
    except ValueError as exc:
        raise CommonsError(str(exc)) from exc
    cert = parse_cert(cert_event)
    await _store_cert(cert_event, await get_owner_id())
    state.zebra_pubkey = cert.zebra_pubkey
    state.device_label = cert.label
    state.sphere = cert.sphere
    state.sphere_observed = cert.observed
    await state.asave()


# ---------------------------------------------------------------------------
# Read model
# ---------------------------------------------------------------------------


async def overview() -> dict[str, Any]:
    """Everything the Commons page shows. Creates the device key on first use."""
    owner_id = await get_owner_id()
    owner = None
    if owner_id is not None:
        owner = await get_user_model().objects.filter(id=owner_id).afirst()
    data: dict[str, Any] = {
        "enabled": commons_enabled(),
        "owner_id": owner_id,
        "owner_name": owner.get_username() if owner else "",
    }
    if not data["enabled"]:
        return data

    state = await _state()
    commons_keys = get_commons_keys()
    device_secret = await _ensure_device(state, commons_keys)
    device_pubkey = keys.public_key(device_secret)
    zebra_secret = await commons_keys.zebra_secret()
    # A held Zebra key always names the identity, even if the DB lost track of it.
    if zebra_secret and state.zebra_pubkey != keys.public_key(zebra_secret):
        state.zebra_pubkey = keys.public_key(zebra_secret)
        await state.asave(update_fields=["zebra_pubkey"])

    devices: list[dict[str, Any]] = []
    this_device_status = "unpaired"
    if state.zebra_pubkey:
        events = await _chain_events(state.zebra_pubkey)
        rows = CommonsDeviceModel.objects.filter(zebra_pubkey=state.zebra_pubkey).order_by(
            "created_at"
        )
        async for row in rows:
            result = verify_device_chain(row.device_pubkey, state.zebra_pubkey, events)
            status = "verified" if result.ok else result.reason
            is_local = row.device_pubkey == device_pubkey
            if is_local:
                this_device_status = status
            devices.append(
                {
                    "pubkey": row.device_pubkey,
                    "npub": keys.npub_encode(row.device_pubkey),
                    "fingerprint": fingerprint(row.device_pubkey),
                    "label": row.label,
                    "sphere": row.sphere,
                    "observed": row.observed,
                    "expires_at": row.expires_at,
                    "revoked_at": row.revoked_at,
                    "status": status,
                    "is_local": is_local,
                }
            )

    data.update(
        {
            "has_identity": bool(state.zebra_pubkey),
            "zebra_pubkey": state.zebra_pubkey,
            "zebra_npub": keys.npub_encode(state.zebra_pubkey) if state.zebra_pubkey else "",
            "zebra_fingerprint": fingerprint(state.zebra_pubkey) if state.zebra_pubkey else "",
            "zebra_display_name": state.zebra_display_name,
            "holds_zebra_key": zebra_secret is not None,
            "device": {
                "pubkey": device_pubkey,
                "pairing_code": pairing_code(device_pubkey),
                "fingerprint": fingerprint(device_pubkey),
                "label": state.device_label,
                "sphere": state.sphere,
                "observed": state.sphere_observed,
                "status": this_device_status,
            },
            "sync_direction": state.sync_direction,
            "devices": devices,
        }
    )
    return data


# ---------------------------------------------------------------------------
# Actions (owner only, Commons enabled: checked by the views)
# ---------------------------------------------------------------------------


async def start_zebra(*, display_name: str, label: str, sphere: str, observed: bool) -> str:
    """Create this deployment's Zebra key and certify this device. Returns the Zebra npub."""
    state = await _state()
    if state.zebra_pubkey:
        raise CommonsError("This deployment already has a Zebra identity.")
    commons_keys = get_commons_keys()
    device_secret = await _ensure_device(state, commons_keys)
    zebra_secret = await commons_keys.zebra_secret() or await commons_keys.create_zebra_secret()
    state.zebra_display_name = (display_name or "").strip()[:255]
    await _self_certify(
        state, zebra_secret, device_secret, label=label, sphere=sphere, observed=observed
    )
    return keys.npub_encode(state.zebra_pubkey)


async def pair_device(
    *,
    code: str,
    label: str,
    sphere: str,
    observed: bool,
    expires_at: int | None = None,
) -> dict[str, str]:
    """Certify another device (or re-certify one, e.g. to change its sphere).

    Returns the cert code to paste on that device and its fingerprint.
    """
    state = await _state()
    zebra_secret = await get_commons_keys().zebra_secret()
    if zebra_secret is None:
        raise CommonsError("Only a device holding the Zebra key can pair devices.")
    try:
        device_pubkey = parse_pairing_code(code)
    except ValueError as exc:
        raise CommonsError("That pairing code is not valid.") from exc
    zebra_pubkey = keys.public_key(zebra_secret)
    existing = await CommonsDeviceModel.objects.filter(
        zebra_pubkey=zebra_pubkey, device_pubkey=device_pubkey
    ).afirst()
    if existing is not None and existing.revoke_event:
        raise CommonsError("That device was revoked. Pair it again with a new device key.")
    if expires_at is not None and expires_at <= int(datetime.now(UTC).timestamp()):
        raise CommonsError("The expiry must be in the future.")
    try:
        cert_event = make_device_cert(
            zebra_secret,
            device_pubkey,
            label=label,
            sphere=sphere,
            observed=observed,
            expires_at=expires_at,
        )
    except ValueError as exc:
        raise CommonsError(str(exc)) from exc
    await _store_cert(cert_event, await get_owner_id())
    if device_pubkey == state.device_pubkey:
        cert = parse_cert(cert_event)
        state.device_label, state.sphere, state.sphere_observed = (
            cert.label,
            cert.sphere,
            cert.observed,
        )
        await state.asave(update_fields=["device_label", "sphere", "sphere_observed"])
    return {"cert_code": encode_cert_code(cert_event), "fingerprint": fingerprint(device_pubkey)}


async def import_cert(cert_code: str) -> str:
    """On a newly paired device: verify and adopt a cert made for it. Returns the Zebra npub."""
    try:
        event = decode_cert_code(cert_code)
    except ValueError as exc:
        raise CommonsError("That certificate code is not valid.") from exc
    cert = parse_cert(event)
    if cert is None or not verify_event(event):
        raise CommonsError("That certificate is not correctly signed.")
    state = await _state()
    commons_keys = get_commons_keys()
    device_secret = await _ensure_device(state, commons_keys)
    if cert.device_pubkey != keys.public_key(device_secret):
        raise CommonsError("That certificate is for a different device.")
    result = verify_device_chain(cert.device_pubkey, cert.zebra_pubkey, [event])
    if not result.ok:
        raise CommonsError(f"That certificate is not valid ({result.reason}).")
    held = await commons_keys.zebra_secret()
    if held is not None and keys.public_key(held) != cert.zebra_pubkey:
        raise CommonsError(
            "This device holds its own Zebra key, so it cannot join another Zebra. "
            "Restore that Zebra's backup here instead."
        )
    await _store_cert(event, await get_owner_id())
    state.zebra_pubkey = cert.zebra_pubkey
    state.device_label = cert.label
    state.sphere = cert.sphere
    state.sphere_observed = cert.observed
    await state.asave()
    return keys.npub_encode(cert.zebra_pubkey)


async def revoke_device(device_pubkey: str, reason: str = "") -> None:
    """Revoke a lost or retired device. Its signatures are rejected from now on."""
    state = await _state()
    zebra_secret = await get_commons_keys().zebra_secret()
    if zebra_secret is None:
        raise CommonsError("Only a device holding the Zebra key can revoke devices.")
    if device_pubkey == state.device_pubkey:
        raise CommonsError("This device cannot revoke itself.")
    zebra_pubkey = keys.public_key(zebra_secret)
    row = await CommonsDeviceModel.objects.filter(
        zebra_pubkey=zebra_pubkey, device_pubkey=device_pubkey
    ).afirst()
    if row is None:
        raise CommonsError("Unknown device.")
    if row.revoke_event:
        return
    revoke = make_device_revoke(zebra_secret, device_pubkey, reason=reason)
    row.revoke_event = revoke.to_dict()
    row.revoked_at = datetime.fromtimestamp(revoke.created_at, UTC)
    await row.asave(update_fields=["revoke_event", "revoked_at", "updated_at"])
    logger.info("Revoked Commons device %s", device_pubkey[:16])


async def export_backup() -> str:
    """The Zebra key as an ``nsec``. A secret: never log it."""
    try:
        return await get_commons_keys().export_backup()
    except ValueError as exc:
        raise CommonsError(str(exc)) from exc


async def restore_backup(nsec: str) -> str:
    """Restore the Zebra key from an ``nsec`` and re-certify this device. Returns the npub."""
    try:
        keys.nsec_decode(nsec)
    except keys.InvalidKeyError as exc:
        raise CommonsError("That is not a valid Zebra key backup (nsec).") from exc
    state = await _state()
    commons_keys = get_commons_keys()
    device_secret = await _ensure_device(state, commons_keys)
    await commons_keys.restore_backup(nsec)
    zebra_secret = await commons_keys.zebra_secret()
    await _self_certify(
        state,
        zebra_secret,
        device_secret,
        label=state.device_label or "This device",
        sphere=state.sphere or "home",
        observed=state.sphere_observed,
    )
    return keys.npub_encode(state.zebra_pubkey)
