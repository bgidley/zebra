"""Commons identity page and service (#228): start, pair, join, revoke, owner, backup.

Two deployments are simulated in one test database by switching the Commons key
directory and wiping the Commons rows between "devices".
"""

from __future__ import annotations

import logging
import re
from urllib.parse import unquote_plus

import pytest
from zebra_agent.commons import keys
from zebra_agent.commons.events import Event, sign_event
from zebra_agent.commons.identity import (
    decode_cert_code,
    encode_cert_code,
    make_device_cert,
    verify_attributed,
    verify_device_chain,
)
from zebra_agent.commons.keystore import CommonsKeys
from zebra_agent.storage.credentials import FileCredentialStore
from zebra_agent_web.api.models import CommonsDeviceModel, SystemStateModel

COMMONS_STATE_FIELDS = {
    "zebra_pubkey": "",
    "zebra_display_name": "",
    "device_pubkey": "",
    "device_label": "",
    "sphere": "",
    "sphere_observed": False,
    "sync_direction": "both",
    "commons_owner_user_id": None,
}


@pytest.fixture(autouse=True)
def completed_setup(db):
    from zebra_agent_web.api.identity import set_identity_sync

    set_identity_sync("Test User")


@pytest.fixture
def commons(settings, tmp_path):
    """Turn Commons on and switch between simulated deployments by key directory."""

    def use(device: str, *, enabled: bool = True, fresh_db: bool = False):
        if fresh_db:
            CommonsDeviceModel.objects.all().delete()
            SystemStateModel.objects.filter(pk=1).update(**COMMONS_STATE_FIELDS)
        settings.ZEBRA_AGENT_SETTINGS = {
            **settings.ZEBRA_AGENT_SETTINGS,
            "COMMONS_ENABLED": enabled,
            "COMMONS_KEY_DIR": str(tmp_path / device),
        }
        return tmp_path / device

    use("a")
    return use


def _keys(path) -> CommonsKeys:
    return CommonsKeys(FileCredentialStore(path))


def _chain_events(zebra_pubkey: str) -> list[Event]:
    events = []
    for row in CommonsDeviceModel.objects.filter(zebra_pubkey=zebra_pubkey):
        events.append(Event.from_dict(row.cert_event))
        if row.revoke_event:
            events.append(Event.from_dict(row.revoke_event))
    return events


# Every Commons action POST (start, pair, import, revoke, backup, restore), #268.
COMMONS_ACTION_URLS = [
    "/commons/start/",
    "/commons/pair/",
    "/commons/import/",
    f"/commons/devices/{'a' * 64}/revoke/",
    "/commons/backup/",
    "/commons/restore/",
]


async def _start(client, **overrides):
    data = {"label": "Home server", "managed_by": "me", "sphere": "home", **overrides}
    return await client.post("/commons/start/", data)


@pytest.mark.django_db(transaction=True)
async def test_off_by_default_creates_nothing(authenticated_async_client, settings, tmp_path):
    settings.ZEBRA_AGENT_SETTINGS = {
        **settings.ZEBRA_AGENT_SETTINGS,
        "COMMONS_KEY_DIR": str(tmp_path / "keys"),
    }
    from django.conf import settings as live

    assert live.ZEBRA_AGENT_SETTINGS["COMMONS_ENABLED"] is False

    response = await authenticated_async_client.get("/commons/")
    assert response.status_code == 200
    html = response.content.decode()
    assert 'data-testid="commons-off"' in html
    assert 'href="/commons/"' not in html  # nav link hidden

    for url in COMMONS_ACTION_URLS:
        assert (await authenticated_async_client.post(url, {})).status_code == 404, url
    assert not (tmp_path / "keys").exists()


@pytest.mark.django_db(transaction=True)
async def test_turning_off_over_existing_keys_disables_every_action(
    authenticated_async_client, commons
):
    """#268: a deployment with keys that turns Commons off answers 404 and keeps its keys."""
    key_dir = commons("a")
    assert (await _start(authenticated_async_client)).status_code == 302
    before = {p.name: p.read_bytes() for p in key_dir.rglob("*") if p.is_file()}
    assert before

    commons("a", enabled=False)
    for url in COMMONS_ACTION_URLS:
        response = await authenticated_async_client.post(url, {"nsec": "x", "code": "x"})
        assert response.status_code == 404, url
    assert {p.name: p.read_bytes() for p in key_dir.rglob("*") if p.is_file()} == before


@pytest.mark.django_db(transaction=True)
async def test_start_shows_npub_owner_and_one_device(
    authenticated_async_client, commons, test_user
):
    key_dir = commons("a")
    response = await _start(authenticated_async_client, display_name="Ben's Zebra")
    assert response.status_code == 302

    html = (await authenticated_async_client.get("/commons/")).content.decode()
    state = SystemStateModel.objects.get(pk=1)
    zebra_secret = await _keys(key_dir).zebra_secret()
    device_secret = await _keys(key_dir).device_secret()

    # Secrets live in the credential store; the DB holds only public keys.
    assert state.zebra_pubkey == keys.public_key(zebra_secret)
    assert state.device_pubkey == keys.public_key(device_secret)
    assert state.commons_owner_user_id == test_user.id
    for field in SystemStateModel._meta.fields:
        value = str(getattr(state, field.name))
        assert zebra_secret not in value and device_secret not in value

    assert keys.npub_encode(state.zebra_pubkey) in html
    assert 'data-testid="commons-owner">testuser<' in html
    assert html.count("data-device=") == 1
    assert 'data-status="verified"' in html
    assert 'href="/commons/"' in html  # nav link shown when on
    assert response["Location"].startswith("/commons/?message=")

    # A second start is refused.
    again = await _start(authenticated_async_client)
    assert "error=" in again["Location"]


@pytest.mark.django_db(transaction=True)
async def test_pair_work_device_join_and_revoke(authenticated_async_client, commons, caplog):
    caplog.set_level(logging.DEBUG)

    # Device B (fresh deployment): its page shows a pairing code.
    b_dir = commons("b")
    html = (await authenticated_async_client.get("/commons/")).content.decode()
    code = re.search(r'data-testid="pairing-code">(npub1[0-9a-z]+)<', html).group(1)
    b_secret = await _keys(b_dir).device_secret()
    b_pub = keys.public_key(b_secret)
    assert keys.npub_encode(b_pub) == code

    # Device A: start the Zebra and pair B as work, managed by someone else.
    a_dir = commons("a", fresh_db=True)
    await _start(authenticated_async_client)
    z_pub = SystemStateModel.objects.get(pk=1).zebra_pubkey
    response = await authenticated_async_client.post(
        "/commons/pair/",
        {"code": code, "label": "Work laptop", "managed_by": "someone_else", "sphere": "work"},
    )
    assert response.status_code == 200
    html = response.content.decode()
    cert_code = re.search(r'data-testid="cert-code"[^>]*>\s*(zcert1[^<\s]+)', html).group(1)

    result = verify_device_chain(b_pub, z_pub, _chain_events(z_pub))
    assert result.ok and result.cert.sphere == "work" and result.cert.observed is True
    page = (await authenticated_async_client.get("/commons/")).content.decode()
    assert page.count("data-device=") == 2
    assert "observed: managed by someone else" in page

    a_state = {
        "rows": list(CommonsDeviceModel.objects.values()),
        "state": SystemStateModel.objects.filter(pk=1).values().first(),
    }

    # Device B imports the cert and joins A's Zebra.
    commons("b", fresh_db=True)
    tampered = cert_code[:-4] + ("BBBB" if cert_code.endswith("AAAA") else "AAAA")
    other = await authenticated_async_client.post("/commons/import/", {"cert_code": tampered})
    assert "error=" in other["Location"]
    joined = await authenticated_async_client.post("/commons/import/", {"cert_code": cert_code})
    assert "error=" not in joined["Location"]
    b_state = SystemStateModel.objects.get(pk=1)
    assert b_state.zebra_pubkey == z_pub
    assert (b_state.sphere, b_state.sphere_observed, b_state.device_label) == (
        "work",
        True,
        "Work laptop",
    )
    page = (await authenticated_async_client.get("/commons/")).content.decode()
    assert keys.npub_encode(z_pub) in page
    assert 'data-status="verified"' in page

    # Back on A: revoke B.
    commons("a", fresh_db=True)
    for row in a_state["rows"]:
        CommonsDeviceModel.objects.create(**row)
    SystemStateModel.objects.filter(pk=1).update(
        **{k: a_state["state"][k] for k in COMMONS_STATE_FIELDS}
    )
    a_local = SystemStateModel.objects.get(pk=1).device_pubkey
    revoke = await authenticated_async_client.post(
        f"/commons/devices/{b_pub}/revoke/", {"reason": "lost"}
    )
    assert "error=" not in revoke["Location"]

    events = _chain_events(z_pub)
    signed_by_b = sign_event(b_secret, 1, [], "an offer")
    assert verify_attributed(signed_by_b, z_pub, events).reason == "revoked"
    assert verify_device_chain(a_local, z_pub, events).ok
    assert SystemStateModel.objects.get(pk=1).zebra_pubkey == z_pub
    page = (await authenticated_async_client.get("/commons/")).content.decode()
    assert 'data-status="revoked"' in page

    # A revoked key cannot be paired again; the local device cannot revoke itself.
    again = await authenticated_async_client.post(
        "/commons/pair/", {"code": code, "label": "x", "managed_by": "me", "sphere": "home"}
    )
    assert again.status_code == 302 and "revoked" in again["Location"]
    self_revoke = await authenticated_async_client.post(f"/commons/devices/{a_local}/revoke/")
    assert "error=" in self_revoke["Location"]

    assert await _keys(a_dir).zebra_secret() not in caplog.text


@pytest.mark.django_db(transaction=True)
async def test_non_owner_gets_403(async_client, commons, test_user):
    from django.contrib.auth import get_user_model

    other = get_user_model().objects.create_user(username="guest")
    async_client.force_login(other)
    commons("a")
    for url in [
        "/commons/start/",
        "/commons/pair/",
        "/commons/import/",
        "/commons/backup/",
        "/commons/restore/",
        f"/commons/devices/{'a' * 64}/revoke/",
    ]:
        assert (await async_client.post(url, {})).status_code == 403, url
    html = (await async_client.get("/commons/")).content.decode()
    assert 'data-testid="not-owner"' in html
    assert "nsec1" not in html
    assert SystemStateModel.objects.get(pk=1).zebra_pubkey == ""


@pytest.mark.django_db(transaction=True)
async def test_backup_restore_on_fresh_deployment(authenticated_async_client, commons, caplog):
    caplog.set_level(logging.DEBUG)
    commons("a")
    await _start(authenticated_async_client)
    z_pub = SystemStateModel.objects.get(pk=1).zebra_pubkey

    response = await authenticated_async_client.post("/commons/backup/")
    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    nsec = re.search(
        r'data-testid="backup-nsec"[^>]*>\s*(nsec1[0-9a-z]+)', response.content.decode()
    )
    nsec = nsec.group(1)
    assert nsec not in caplog.text

    # A fresh deployment restores the backup: same npub, its own device re-certified.
    commons("c", fresh_db=True)
    bad = await authenticated_async_client.post("/commons/restore/", {"nsec": "nsec1nope"})
    assert "error=" in bad["Location"]
    assert SystemStateModel.objects.get(pk=1).zebra_pubkey == ""

    ok = await authenticated_async_client.post("/commons/restore/", {"nsec": nsec})
    assert "error=" not in ok["Location"]
    state = SystemStateModel.objects.get(pk=1)
    assert state.zebra_pubkey == z_pub
    assert verify_device_chain(state.device_pubkey, z_pub, _chain_events(z_pub)).ok
    assert nsec not in caplog.text


@pytest.mark.django_db(transaction=True)
async def test_switching_off_keeps_keys(authenticated_async_client, commons):
    commons("a")
    await _start(authenticated_async_client)
    z_pub = SystemStateModel.objects.get(pk=1).zebra_pubkey

    commons("a", enabled=False)
    html = (await authenticated_async_client.get("/commons/")).content.decode()
    assert 'data-testid="commons-off"' in html

    commons("a", enabled=True)
    html = (await authenticated_async_client.get("/commons/")).content.decode()
    assert keys.npub_encode(z_pub) in html


def _commons_snapshot() -> dict:
    return {
        "rows": list(CommonsDeviceModel.objects.order_by("id").values()),
        "state": {
            k: v
            for k, v in SystemStateModel.objects.filter(pk=1).values().first().items()
            if k in COMMONS_STATE_FIELDS
        },
    }


@pytest.mark.django_db(transaction=True)
async def test_import_rejects_replayed_tampered_expired_and_foreign_certs(
    authenticated_async_client, commons
):
    """O2: a cert only joins the device it names, signed by its Zebra, unaltered and unexpired.

    Every code below decodes, so each rejection comes from the signature, device or
    chain check in ``import_cert``, not from a corrupted code.
    """
    # Device B and device C each have their own device key.
    commons("b", fresh_db=True)
    await authenticated_async_client.get("/commons/")
    b_pub = SystemStateModel.objects.get(pk=1).device_pubkey
    c_dir = commons("c", fresh_db=True)
    await authenticated_async_client.get("/commons/")
    c_pub = SystemStateModel.objects.get(pk=1).device_pubkey
    assert b_pub and c_pub and b_pub != c_pub

    z_secret = keys.generate_secret_key()
    z_pub = keys.public_key(z_secret)

    def cert_for(device, *, secret=z_secret, **kwargs):
        params = {"label": "Laptop", "sphere": "work", "observed": True, **kwargs}
        return make_device_cert(secret, device, **params)

    valid_for_b = cert_for(b_pub)
    valid_for_c = cert_for(c_pub)
    tampered_content = Event.from_dict(
        {**valid_for_c.to_dict(), "content": valid_for_c.content.replace("work", "home")}
    )
    flipped = "0" if valid_for_c.sig[-1] != "0" else "1"
    tampered_sig = Event.from_dict({**valid_for_c.to_dict(), "sig": valid_for_c.sig[:-1] + flipped})
    # Signed by another key but claiming the Zebra key as its signer.
    foreign_signed = Event.from_dict(
        {**cert_for(c_pub, secret=keys.generate_secret_key()).to_dict(), "pubkey": z_pub}
    )
    expired = cert_for(c_pub, expires_at=1_000_000_000)

    cases = {
        "replayed onto another device": (valid_for_b, "for a different device"),
        "changed content": (tampered_content, "not correctly signed"),
        "changed sig": (tampered_sig, "not correctly signed"),
        "signed by a key other than the Zebra key": (foreign_signed, "not correctly signed"),
        "expired": (expired, "expired"),
    }
    before = _commons_snapshot()
    for name, (event, reason) in cases.items():
        code = encode_cert_code(event)
        assert decode_cert_code(code).to_dict() == event.to_dict(), name
        response = await authenticated_async_client.post("/commons/import/", {"cert_code": code})
        assert response.status_code == 302, name
        location = unquote_plus(response["Location"])
        assert "error=" in location and reason in location, (name, location)
        assert _commons_snapshot() == before, name
    assert await _keys(c_dir).zebra_secret() is None

    # The genuine cert for C is accepted.
    ok = await authenticated_async_client.post(
        "/commons/import/", {"cert_code": encode_cert_code(valid_for_c)}
    )
    assert "error=" not in ok["Location"]
    assert SystemStateModel.objects.get(pk=1).zebra_pubkey == z_pub

    # Once C belongs to Z, a valid cert from a different Zebra cannot take it over.
    joined = _commons_snapshot()
    other_zebra = cert_for(c_pub, secret=keys.generate_secret_key())
    response = await authenticated_async_client.post(
        "/commons/import/", {"cert_code": encode_cert_code(other_zebra)}
    )
    assert "another Zebra" in unquote_plus(response["Location"])
    assert _commons_snapshot() == joined
