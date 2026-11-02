"""Tests for Commons S1 identity: keys, events, certs, revokes and the keystore (#228)."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from zebra_agent.commons import keys
from zebra_agent.commons.events import Event, sign_event, verify_event
from zebra_agent.commons.identity import (
    DEVICE_CERT_KIND,
    decode_cert_code,
    encode_cert_code,
    fingerprint,
    make_device_cert,
    make_device_revoke,
    pairing_code,
    parse_pairing_code,
    verify_attributed,
    verify_device_chain,
)
from zebra_agent.commons.keystore import (
    DEVICE_KEY_INTEGRATION,
    INSTANCE_NAMESPACE,
    SECRET_KEY_TYPE,
    ZEBRA_KEY_INTEGRATION,
    CommonsKeys,
)
from zebra_agent.storage.interfaces import InMemoryCredentialStore

# ---------------------------------------------------------------------------
# Keys: BIP-340 and NIP-19 test vectors
# ---------------------------------------------------------------------------

# From the BIP-340 test vectors (index 0 and 1).
BIP340_VECTORS = [
    (
        "0000000000000000000000000000000000000000000000000000000000000003",
        "f9308a019258c31049344f85f89d5229b531c845836f99b08601f113bce036f9",
        "0000000000000000000000000000000000000000000000000000000000000000",
        "e907831f80848d1069a5371b402410364bdf1c5f8307b0084c55f1ce2dca8215"
        "25f66a4a85ea8b71e482a74f382d2ce5ebeee8fdb2172f477df4900d310536c0",
    ),
    (
        "b7e151628aed2a6abf7158809cf4f3c762e7160f38b4da56a784d9045190cfef",
        "dff1d77f2a671c5f36183726db2341be58feae1da2deced843240f7b502ba659",
        "243f6a8885a308d313198a2e03707344a4093822299f31d0082efa98ec4e6c89",
        "6896bd60eeae296db48a229ff71dfe071bde413e6d43f917dc8dcf8c78de3341"
        "8906d11ac976abccb20b091292bff4ea897efcb639ea871cfa95f6de339e4b0a",
    ),
]


@pytest.mark.parametrize("secret,pubkey,msg,sig", BIP340_VECTORS)
def test_bip340_vectors_pubkey_and_verify(secret, pubkey, msg, sig):
    assert keys.public_key(secret) == pubkey
    assert keys.verify(pubkey, bytes.fromhex(msg), sig)
    # Our own signatures (fresh aux randomness) verify too.
    assert keys.verify(pubkey, bytes.fromhex(msg), keys.sign(secret, bytes.fromhex(msg)))


def test_bip340_rejects_wrong_message_and_garbage():
    secret, pubkey, msg, sig = BIP340_VECTORS[0]
    assert not keys.verify(pubkey, b"\x01" * 32, sig)
    assert not keys.verify(pubkey, bytes.fromhex(msg), "00" * 64)
    assert not keys.verify("zz", bytes.fromhex(msg), sig)
    assert not keys.verify(pubkey, bytes.fromhex(msg), "abc")


def test_generated_keys_are_valid_and_distinct():
    a, b = keys.generate_secret_key(), keys.generate_secret_key()
    assert a != b
    assert keys.is_valid_public_key(keys.public_key(a))


def test_nip19_vectors():
    pub = "3bf0c63fcb93463407af97a5e5ee64fa883d107ef9e558472c4eb9aaaefa459d"
    npub = "npub180cvv07tjdrrgpa0j7j7tmnyl2yr6yr7l8j4s3evf6u64th6gkwsyjh6w6"
    sec = "67dea2ed018072d675f5415ecfaed7d2597555e202d85b3d65ea4e58d2d92ffa"
    nsec = "nsec1vl029mgpspedva04g90vltkh6fvh240zqtv9k0t9af8935ke9laqsnlfe5"
    assert keys.npub_encode(pub) == npub
    assert keys.npub_decode(npub) == pub
    assert keys.nsec_encode(sec) == nsec
    assert keys.nsec_decode(nsec) == sec


@pytest.mark.parametrize(
    "text",
    [
        "",
        "nsec1",
        "npub180cvv07tjdrrgpa0j7j7tmnyl2yr6yr7l8j4s3evf6u64th6gkwsyjh6w6",  # wrong hrp
        "nsec1vl029mgpspedva04g90vltkh6fvh240zqtv9k0t9af8935ke9laqsnlfe6",  # bad checksum
        "not a key at all",
    ],
)
def test_nsec_decode_rejects_invalid(text):
    with pytest.raises(keys.InvalidKeyError):
        keys.nsec_decode(text)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


def test_event_sign_verify_and_round_trip():
    secret = keys.generate_secret_key()
    event = sign_event(secret, 1, [["t", "x"]], "héllo", created_at=1_700_000_000)
    assert verify_event(event)
    again = Event.from_dict(json.loads(json.dumps(event.to_dict())))
    assert again == event and verify_event(again)


def test_tampered_event_fails():
    event = sign_event(keys.generate_secret_key(), 1, [], "a", created_at=1)
    assert not verify_event(replace(event, content="b"))
    other = keys.public_key(keys.generate_secret_key())
    assert not verify_event(replace(event, pubkey=other))


# ---------------------------------------------------------------------------
# Certs, revokes and chain verification
# ---------------------------------------------------------------------------


@pytest.fixture
def zebra():
    secret = keys.generate_secret_key()
    return secret, keys.public_key(secret)


@pytest.fixture
def device():
    secret = keys.generate_secret_key()
    return secret, keys.public_key(secret)


def test_cert_chain_accepts_paired_work_device(zebra, device):
    z_sec, z_pub = zebra
    d_sec, d_pub = device
    cert = make_device_cert(z_sec, d_pub, label="Work laptop", sphere="Work", observed=True)
    assert cert.kind == DEVICE_CERT_KIND
    result = verify_device_chain(d_pub, z_pub, [cert])
    assert result.ok and result.reason == "ok"
    assert result.cert.sphere == "work"
    assert result.cert.observed is True
    assert result.cert.label == "Work laptop"

    # An event signed by the device is attributed to the Zebra.
    offer = sign_event(d_sec, 1, [], "hello")
    assert verify_attributed(offer, z_pub, [cert]).ok


def test_cert_from_foreign_key_or_tampered_is_rejected(zebra, device):
    z_sec, z_pub = zebra
    _, d_pub = device
    foreign = make_device_cert(
        keys.generate_secret_key(), d_pub, label="x", sphere="home", observed=False
    )
    assert verify_device_chain(d_pub, z_pub, [foreign]).reason == "no_cert"

    cert = make_device_cert(z_sec, d_pub, label="x", sphere="home", observed=False)
    tampered = replace(cert, content=cert.content.replace("home", "work"))
    assert verify_device_chain(d_pub, z_pub, [tampered]).reason == "no_cert"

    # A cert naming another device does not certify this one.
    other_pub = keys.public_key(keys.generate_secret_key())
    other = make_device_cert(z_sec, other_pub, label="x", sphere="home", observed=False)
    assert verify_device_chain(d_pub, z_pub, [other]).reason == "no_cert"


def test_expired_cert_is_rejected(zebra, device):
    z_sec, z_pub = zebra
    _, d_pub = device
    cert = make_device_cert(
        z_sec, d_pub, label="x", sphere="home", observed=False, expires_at=1_000
    )
    assert verify_device_chain(d_pub, z_pub, [cert], now=999).ok
    assert verify_device_chain(d_pub, z_pub, [cert], now=1_000).reason == "expired"


def test_newest_cert_wins(zebra, device):
    z_sec, z_pub = zebra
    _, d_pub = device
    old = make_device_cert(z_sec, d_pub, label="x", sphere="home", observed=False, created_at=10)
    new = make_device_cert(z_sec, d_pub, label="x", sphere="work", observed=True, created_at=20)
    result = verify_device_chain(d_pub, z_pub, [new, old])
    assert result.cert.sphere == "work"


def test_revoked_device_signatures_rejected_outright(zebra, device):
    z_sec, z_pub = zebra
    d_sec, d_pub = device
    keep_sec = keys.generate_secret_key()
    keep_pub = keys.public_key(keep_sec)
    certs = [
        make_device_cert(z_sec, d_pub, label="lost", sphere="work", observed=True),
        make_device_cert(z_sec, keep_pub, label="home", sphere="home", observed=False),
    ]
    revoke = make_device_revoke(z_sec, d_pub, reason="lost", created_at=1)
    events = [*certs, revoke]

    signed_by_revoked = sign_event(d_sec, 1, [], "x")
    result = verify_attributed(signed_by_revoked, z_pub, events)
    assert not result.ok and result.reason == "revoked"
    # Other devices still verify.
    assert verify_attributed(sign_event(keep_sec, 1, [], "x"), z_pub, events).ok

    # A revoke from anyone but the Zebra key is ignored.
    fake = make_device_revoke(keys.generate_secret_key(), keep_pub)
    assert verify_device_chain(keep_pub, z_pub, [*events, fake]).ok


def test_bad_signature_on_attributed_event(zebra, device):
    _, z_pub = zebra
    d_sec, _ = device
    event = sign_event(d_sec, 1, [], "x")
    assert verify_attributed(replace(event, content="y"), z_pub, []).reason == "bad_signature"


def test_cert_rejects_invalid_inputs(zebra):
    z_sec, _ = zebra
    with pytest.raises(ValueError):
        make_device_cert(z_sec, "00" * 32, label="x", sphere="home", observed=False)
    pub = keys.public_key(keys.generate_secret_key())
    with pytest.raises(ValueError):
        make_device_cert(z_sec, pub, label=" ", sphere="home", observed=False)
    with pytest.raises(ValueError):
        make_device_cert(z_sec, pub, label="x", sphere="", observed=False)


def test_pairing_and_cert_codes_round_trip(zebra, device):
    z_sec, _ = zebra
    _, d_pub = device
    code = pairing_code(d_pub)
    assert code.startswith("npub1")
    assert parse_pairing_code(f"  {code} ") == d_pub
    assert len(fingerprint(d_pub)) == 9 and fingerprint(d_pub) == fingerprint(d_pub)

    cert = make_device_cert(z_sec, d_pub, label="x", sphere="home", observed=False)
    cert_code = encode_cert_code(cert)
    assert cert_code.startswith("zcert1")
    # Whitespace from copy-paste is tolerated.
    assert decode_cert_code(cert_code[:20] + "\n" + cert_code[20:]) == cert
    with pytest.raises(ValueError):
        decode_cert_code("zcert1!!!!")
    with pytest.raises(ValueError):
        decode_cert_code("hello")


# ---------------------------------------------------------------------------
# Keystore
# ---------------------------------------------------------------------------


async def test_device_key_created_once_in_credential_store():
    store = InMemoryCredentialStore()
    commons = CommonsKeys(store)
    first = await commons.get_or_create_device_secret()
    assert await commons.get_or_create_device_secret() == first
    assert await store.get(INSTANCE_NAMESPACE, DEVICE_KEY_INTEGRATION, SECRET_KEY_TYPE) == first
    assert "first" not in repr(commons)


async def test_zebra_key_create_backup_restore():
    store = InMemoryCredentialStore()
    commons = CommonsKeys(store)
    assert await commons.zebra_secret() is None
    with pytest.raises(ValueError):
        await commons.export_backup()

    secret = await commons.create_zebra_secret()
    assert await store.get(INSTANCE_NAMESPACE, ZEBRA_KEY_INTEGRATION, SECRET_KEY_TYPE) == secret
    with pytest.raises(ValueError):
        await commons.create_zebra_secret()

    nsec = await commons.export_backup()
    fresh = CommonsKeys(InMemoryCredentialStore())
    assert await fresh.restore_backup(nsec) == keys.public_key(secret)
    assert await fresh.zebra_secret() == secret

    with pytest.raises(keys.InvalidKeyError):
        await fresh.restore_backup("nsec1garbage")
    assert await fresh.zebra_secret() == secret


async def test_keys_survive_restart_in_file_store(tmp_path):
    from zebra_agent.storage.credentials import FileCredentialStore

    first = CommonsKeys(FileCredentialStore(tmp_path))
    device = await first.get_or_create_device_secret()
    zebra_secret = await first.create_zebra_secret()

    # A new process: new store and keystore objects over the same directory.
    second = CommonsKeys(FileCredentialStore(tmp_path))
    assert await second.get_or_create_device_secret() == device
    assert await second.zebra_secret() == zebra_secret
