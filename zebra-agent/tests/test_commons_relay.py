"""Unit tests of the private sync relay pieces (#246): client, outbox, receipts, revocation."""

import json

import pytest

from zebra_agent.commons import keys
from zebra_agent.commons.client import (
    SKILL_KIND,
    Filter,
    InMemoryCommonsClient,
    InMemoryRelay,
    PublishRefused,
)
from zebra_agent.commons.events import COMMONS_TAG, Event, sign_event
from zebra_agent.commons.identity import (
    DEVICE_REVOKE_KIND,
    make_device_cert,
    make_device_revoke,
    verify_attributed,
    verify_device_chain,
)
from zebra_agent.commons.receipts import (
    RECEIPT_KIND,
    ReceiptSigner,
    make_receipt,
    operator_secret_from_env,
    parse_receipt,
    receipt_order,
)
from zebra_agent.commons.relay import (
    Outbox,
    RelayCommonsClient,
    RelayTransport,
    RelayUnavailable,
    SendResult,
)
from zebra_agent.commons.sync import SyncService


class FakeTransport(RelayTransport):
    """A relay in memory that can be down or refuse events with a given message."""

    url = "ws://fake"

    def __init__(self):
        self.stored: list[dict] = []
        self.down = False
        self.refuse: dict[str, str] = {}  # event id -> relay message

    async def send(self, event):
        if self.down:
            raise RelayUnavailable("connection refused")
        if event["id"] in self.refuse:
            return SendResult(False, self.refuse[event["id"]])
        if all(e["id"] != event["id"] for e in self.stored):
            self.stored.append(event)
        return SendResult(True)

    async def query(self, filters):
        if self.down:
            raise RelayUnavailable("connection refused")
        return list(self.stored)


def _event(secret, n, kind=1):
    return sign_event(secret, kind, [["p", "aa"], COMMONS_TAG], f"event {n}", created_at=1000 + n)


@pytest.fixture
def secret():
    return keys.generate_secret_key()


# --- outbox and client -----------------------------------------------------------------


async def test_outage_queues_and_flush_resends_in_order(tmp_path, secret):
    transport = FakeTransport()
    outbox = Outbox(tmp_path / "outbox.jsonl")
    client = RelayCommonsClient(transport, outbox=outbox)
    transport.down = True
    first, second, third = (_event(secret, n) for n in range(3))
    await client.publish(first)
    await client.publish(second)
    assert [e.id for e in outbox.events()] == [first.id, second.id]
    assert transport.stored == []

    transport.down = False
    await client.publish(third)  # behind the queue, never ahead of it
    assert [e["id"] for e in transport.stored] == [first.id, second.id, third.id]
    assert len(outbox) == 0


async def test_queue_survives_a_restart(tmp_path, secret):
    transport = FakeTransport()
    transport.down = True
    event = _event(secret, 1)
    await RelayCommonsClient(transport, outbox=Outbox(tmp_path / "o.jsonl")).publish(event)
    await RelayCommonsClient(transport, outbox=Outbox(tmp_path / "o.jsonl")).publish(event)
    assert len(Outbox(tmp_path / "o.jsonl")) == 1  # queued once

    transport.down = False
    restarted = RelayCommonsClient(transport, outbox=Outbox(tmp_path / "o.jsonl"))
    assert await restarted.flush() == 1
    assert [e["id"] for e in transport.stored] == [event.id]


async def test_flush_stops_while_down(tmp_path, secret):
    transport = FakeTransport()
    outbox = Outbox(tmp_path / "o.jsonl")
    client = RelayCommonsClient(transport, outbox=outbox)
    transport.down = True
    await client.publish(_event(secret, 1))
    assert await client.flush() == 0
    assert len(outbox) == 1


async def test_permanent_refusal_raises_and_is_not_queued(tmp_path, secret):
    transport = FakeTransport()
    outbox = Outbox(tmp_path / "o.jsonl")
    event = _event(secret, 1)
    transport.refuse[event.id] = "blocked: device has no valid cert"
    with pytest.raises(PublishRefused, match="blocked"):
        await RelayCommonsClient(transport, outbox=outbox).publish(event)
    assert len(outbox) == 0


async def test_transient_refusal_is_queued(tmp_path, secret):
    transport = FakeTransport()
    outbox = Outbox(tmp_path / "o.jsonl")
    event = _event(secret, 1)
    transport.refuse[event.id] = "auth-required: authenticate"
    await RelayCommonsClient(transport, outbox=outbox).publish(event)
    assert [e.id for e in outbox.events()] == [event.id]


async def test_queued_event_refused_later_moves_aside(tmp_path, secret):
    transport = FakeTransport()
    outbox = Outbox(tmp_path / "o.jsonl")
    client = RelayCommonsClient(transport, outbox=outbox)
    transport.down = True
    bad, good = _event(secret, 1), _event(secret, 2)
    await client.publish(bad)
    await client.publish(good)
    transport.down = False
    transport.refuse[bad.id] = "blocked: not a registered Zebra key"
    assert await client.flush() == 2
    assert [e["id"] for e in transport.stored] == [good.id]
    rejected = [json.loads(line) for line in outbox.rejected_path.read_text().splitlines()]
    assert rejected[0]["event"]["id"] == bad.id and rejected[0]["reason"].startswith("blocked")


async def test_no_outbox_means_an_outage_raises(secret):
    transport = FakeTransport()
    transport.down = True
    with pytest.raises(RelayUnavailable):
        await RelayCommonsClient(transport).publish(_event(secret, 1))


async def test_fetch_drops_forged_and_unmatched_events(secret):
    transport = FakeTransport()
    good = _event(secret, 1, kind=SKILL_KIND)
    forged = {**_event(secret, 2, kind=SKILL_KIND).to_dict(), "content": "changed"}
    other = _event(secret, 3, kind=7)
    transport.stored = [forged, other.to_dict(), good.to_dict(), {"junk": True}]
    client = RelayCommonsClient(transport)
    assert await client.fetch([Filter(kinds=(SKILL_KIND,))]) == [good]


async def test_hard_filter_still_applies(secret):
    client = RelayCommonsClient(FakeTransport(), private=False)
    with pytest.raises(PublishRefused):
        await client.publish(_event(secret, 1, kind=SKILL_KIND))


def test_filter_to_nostr():
    f = Filter(kinds=(1,), authors=("a",), recipients=("p",), events=("e",), since=5, limit=9)
    assert f.to_nostr() == {
        "kinds": [1],
        "authors": ["a"],
        "#p": ["p"],
        "#e": ["e"],
        "since": 5,
        "limit": 9,
    }


# --- receipts --------------------------------------------------------------------------


def test_receipt_round_trip_and_forgeries(secret):
    operator = keys.generate_secret_key()
    op_pub = keys.public_key(operator)
    receipt = make_receipt(operator, 7, "ab" * 32, SKILL_KIND)
    assert receipt.kind == RECEIPT_KIND
    assert parse_receipt(receipt, op_pub) == ("ab" * 32, 7)

    assert parse_receipt(make_receipt(secret, 7, "ab" * 32, SKILL_KIND), op_pub) is None
    tampered = Event.from_dict({**receipt.to_dict(), "content": '{"seq":1,"event_id":"x"}'})
    assert parse_receipt(tampered, op_pub) is None
    lying = sign_event(
        operator, RECEIPT_KIND, [["e", "cd" * 32], ["seq", "7"]], '{"seq":7,"event_id":"x"}'
    )
    assert parse_receipt(lying, op_pub) is None  # content and tags disagree

    order = receipt_order(
        [
            make_receipt(operator, 9, "ab" * 32, 1),
            make_receipt(operator, 4, "ab" * 32, 1),
            make_receipt(secret, 1, "ab" * 32, 1),
        ],
        op_pub,
    )
    assert order == {"ab" * 32: 4}


def test_operator_secret_from_env():
    secret = keys.generate_secret_key()
    assert operator_secret_from_env({"ZEBRA_SYNC_OPERATOR_SECRET": secret}) == secret
    nsec = keys.nsec_encode(secret)
    assert operator_secret_from_env({"ZEBRA_SYNC_OPERATOR_SECRET": nsec}) == secret
    with pytest.raises(ValueError):
        operator_secret_from_env({})
    with pytest.raises(ValueError):
        operator_secret_from_env({"ZEBRA_SYNC_OPERATOR_SECRET": "zz"})


async def test_receipt_signer_publishes_in_order_and_resumes(tmp_path):
    operator = keys.generate_secret_key()
    journal = tmp_path / "journal.jsonl"
    journal.write_text(
        "".join(
            json.dumps({"seq": n, "id": f"{n:064x}", "kind": SKILL_KIND}) + "\n" for n in (1, 2)
        )
    )
    transport = FakeTransport()
    signer = ReceiptSigner(
        journal, tmp_path / "state.json", RelayCommonsClient(transport), operator
    )
    assert await signer.run_once() == 2
    assert signer.last_seq() == 2
    order = receipt_order([Event.from_dict(e) for e in transport.stored], signer.operator_pubkey)
    assert order == {f"{1:064x}": 1, f"{2:064x}": 2}

    with journal.open("a") as fh:
        fh.write(json.dumps({"seq": 3, "id": f"{3:064x}", "kind": SKILL_KIND}) + "\n")
    transport.down = True
    assert await signer.run_once() == 0  # relay down: nothing lost, retried later
    transport.down = False
    restarted = ReceiptSigner(
        journal, tmp_path / "state.json", RelayCommonsClient(transport), operator
    )
    assert await restarted.run_once() == 1
    assert len(transport.stored) == 3


# --- revocation by receipt order -------------------------------------------------------


@pytest.fixture
def chain():
    zebra = keys.generate_secret_key()
    device = keys.generate_secret_key()
    cert = make_device_cert(zebra, keys.public_key(device), label="lost", sphere="work", observed=1)
    revoke = make_device_revoke(zebra, keys.public_key(device))
    return zebra, device, cert, revoke


def test_revoked_device_judged_by_receipt_order(chain):
    zebra, device, cert, revoke = chain
    zebra_pub, dev_pub = keys.public_key(zebra), keys.public_key(device)
    before, after, unreceipted = (_event(device, n) for n in range(3))
    seqs = {before.id: 5, revoke.id: 9, after.id: 12}
    events = [cert, revoke]

    def check(event, receipt_seq):
        return verify_attributed(event, zebra_pub, events, receipt_seq=receipt_seq).reason

    assert check(before, seqs) == "ok"
    assert check(after, seqs) == "revoked"
    assert check(unreceipted, seqs) == "no_receipt"
    # Without receipts (no relay) the S1 rule: everything from a revoked device is rejected.
    assert check(before, None) == "revoked"
    # A revoke the relay has no receipt for still rejects (it may be newer than anything).
    assert check(before, {before.id: 5}) == "revoked"
    # "May I send to it now?" never passes receipts: a revoked device is out.
    assert verify_device_chain(dev_pub, zebra_pub, events, receipt_seq=seqs).reason == "revoked"


def test_unrevoked_device_needs_no_receipt(chain):
    zebra, device, cert, _ = chain
    event = _event(device, 1)
    assert verify_attributed(event, keys.public_key(zebra), [cert], receipt_seq={}).ok


# --- SyncService over a relay ----------------------------------------------------------


def _service(relay, zebra_pub, device, certs, receipt_pubkey=None, sphere="home"):
    return SyncService(
        client=InMemoryCommonsClient(relay),
        device_secret=device,
        zebra_pubkey=zebra_pub,
        sphere=sphere,
        certs=list(certs),
        receipt_pubkey=receipt_pubkey,
    )


async def test_identity_published_once_and_learnt_from_the_relay():
    zebra = keys.generate_secret_key()
    zebra_pub = keys.public_key(zebra)
    home, work = keys.generate_secret_key(), keys.generate_secret_key()
    home_cert = make_device_cert(zebra, keys.public_key(home), label="h", sphere="home", observed=0)
    work_cert = make_device_cert(zebra, keys.public_key(work), label="w", sphere="work", observed=1)
    stranger = keys.generate_secret_key()
    foreign = make_device_cert(stranger, keys.public_key(home), label="x", sphere="x", observed=0)
    relay = InMemoryRelay()
    home_sync = _service(relay, zebra_pub, home, [home_cert, work_cert, foreign])
    assert await home_sync.publish_identity() == 2  # only this Zebra's own events
    assert await home_sync.publish_identity() == 0
    assert {e.id for e in relay.events} == {home_cert.id, work_cert.id}

    work_sync = _service(relay, zebra_pub, work, [work_cert], sphere="work")
    assert "home" not in work_sync.spheres()
    await work_sync.refresh()
    assert work_sync.spheres() == {"home": False, "work": True}


async def test_refresh_pulls_receipts_for_revokes_and_revoked_senders():
    zebra = keys.generate_secret_key()
    zebra_pub = keys.public_key(zebra)
    operator = keys.generate_secret_key()
    home, lost = keys.generate_secret_key(), keys.generate_secret_key()
    certs = [
        make_device_cert(zebra, keys.public_key(d), label=s, sphere=s, observed=0)
        for d, s in ((home, "home"), (lost, "work"))
    ]
    revoke = make_device_revoke(zebra, keys.public_key(lost))
    early = _event(lost, 1)
    relay = InMemoryRelay()
    for event, seq in ((early, 3), (revoke, 8)):
        relay.store(event)
        relay.store(make_receipt(operator, seq, event.id, event.kind))
    relay.store(make_receipt(keys.generate_secret_key(), 1, revoke.id, DEVICE_REVOKE_KIND))

    sync = _service(relay, zebra_pub, home, certs, receipt_pubkey=keys.public_key(operator))
    await sync.refresh([early])
    assert sync.receipts == {early.id: 3, revoke.id: 8}
    assert revoke in sync.held_events()  # the revoke came from the relay

    no_receipts = _service(relay, zebra_pub, home, certs)
    await no_receipts.refresh([early])
    assert no_receipts.receipts == {}


async def test_refresh_survives_an_unreachable_relay(tmp_path):
    transport = FakeTransport()
    transport.down = True
    zebra = keys.generate_secret_key()
    sync = SyncService(
        client=RelayCommonsClient(transport, outbox=Outbox(tmp_path / "o.jsonl")),
        device_secret=keys.generate_secret_key(),
        zebra_pubkey=keys.public_key(zebra),
        sphere="home",
        receipt_pubkey=keys.public_key(zebra),
    )
    await sync.refresh()  # logs, never raises
    assert await sync.flush() == 0
