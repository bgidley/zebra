"""ATTEST events, offer intake, offer status transitions and the hash-equality rule (#232, S5).

No network: the public relay is an ``InMemoryRelay(private=False)``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zebra_agent.commons import keys
from zebra_agent.commons.attest import (
    LABELS,
    REASONS,
    AttestRefused,
    attest_tags,
    build_attest,
    verify_attest,
)
from zebra_agent.commons.client import Filter, InMemoryCommonsClient, InMemoryRelay
from zebra_agent.commons.events import Event, sign_event
from zebra_agent.commons.exchange import CommonsExchange, attestation_summary, own_offers
from zebra_agent.commons.identity import make_device_cert, make_device_revoke
from zebra_agent.commons.kinds import ATTEST_KIND
from zebra_agent.commons.mirror import InMemoryCommonsMirror
from zebra_agent.commons.offer import (
    build_offer,
    offer_as_export,
    offer_content,
    offer_input,
    offer_stats,
)
from zebra_agent.commons.offers import (
    ADOPTED,
    DELISTED,
    JUDGING,
    REJECTED,
    SEEN,
    InMemoryOfferStore,
    InvalidOfferTransition,
    OfferRecord,
)
from zebra_agent.commons.publisher import CommonsPublisher
from zebra_agent.commons.receipts import make_receipt
from zebra_agent.library import WorkflowLibrary
from zebra_agent.metrics import WorkflowStats
from zebra_agent.provenance import content_sha256

YAML = """name: Capital Facts
description: Answer questions about capital cities
version: 1
first_task: answer
tasks:
  answer:
    name: Answer
    action: llm_call
    properties:
      prompt: "Answer: {{goal}}"
"""
GOLDEN = [{"goal": "What is the capital of Australia?", "expected": "Canberra", "criteria": ["c"]}]
SHA = content_sha256(YAML)


def _zebra() -> dict:
    zebra_secret, device_secret = keys.generate_secret_key(), keys.generate_secret_key()
    cert = make_device_cert(
        zebra_secret, keys.public_key(device_secret), label="Home", sphere="home", observed=False
    )
    return {
        "zebra_secret": zebra_secret,
        "zebra": keys.public_key(zebra_secret),
        "device": device_secret,
        "cert": cert,
    }


def _content(yaml_text: str = YAML) -> dict:
    return offer_content(
        name="Capital Facts",
        summary="Answers capital-city questions.",
        use_when="A question about a capital",
        stats=offer_stats(WorkflowStats("Capital Facts", 5, 5, 4.5), 0.9),
        actions=["llm_call"],
        golden_tasks=GOLDEN,
        yaml=yaml_text,
    )


def _offer(z: dict, content: dict | None = None) -> Event:
    return build_offer(
        content or _content(), device_secret=z["device"], zebra_pubkey=z["zebra"], chain=[z["cert"]]
    )


def _publisher(z: dict, relay: InMemoryRelay, operator: str | None = None) -> CommonsPublisher:
    return CommonsPublisher(
        canonical=InMemoryCommonsClient(relay),
        device_secret=z["device"],
        zebra_pubkey=z["zebra"],
        mirror=InMemoryCommonsMirror(),
        certs=[z["cert"]],
        receipt_pubkey=operator,
        receipt_wait=0,
    )


@pytest.fixture
def relay() -> InMemoryRelay:
    return InMemoryRelay(private=False)


# -- ATTEST build / verify -------------------------------------------------------------------


@pytest.mark.parametrize("label", LABELS)
def test_attest_round_trip(label):
    z = _zebra()
    event = build_attest(
        label, SHA, device_secret=z["device"], zebra_pubkey=z["zebra"], chain=[z["cert"]]
    )
    assert event.kind == ATTEST_KIND
    assert ["L", "zebra-commons"] in event.tags and ["l", label, "zebra-commons"] in event.tags
    check = verify_attest(event, [z["cert"]])
    assert check.ok and check.zebra_pubkey == z["zebra"]
    assert (check.label, check.content_sha256) == (label, SHA)
    assert check.attest_reason == REASONS[label][0]
    assert json.loads(event.content) == {"reason": REASONS[label][0]}


def test_attest_rating_and_vocabulary():
    z = _zebra()
    kw = {"device_secret": z["device"], "zebra_pubkey": z["zebra"], "chain": [z["cert"]]}
    event = build_attest("worked", SHA, rating=4, **kw)
    assert verify_attest(event, [z["cert"]]).rating == 4
    for bad in (
        {"reason": "the goal was about Jane"},
        {"reason": "ethics-review"},  # a reason of another label
        {"rating": 6},
        {"rating": True},
    ):
        with pytest.raises(AttestRefused):
            build_attest("worked", SHA, **{**kw, **bad})
    with pytest.raises(AttestRefused):
        build_attest("loved-it", SHA, **kw)
    with pytest.raises(AttestRefused):
        build_attest("worked", "not-a-hash", **kw)


def test_attest_refuses_an_uncertified_device():
    z, other = _zebra(), _zebra()
    with pytest.raises(AttestRefused, match="not attributed"):
        build_attest(
            "adopted", SHA, device_secret=other["device"], zebra_pubkey=z["zebra"], chain=[]
        )


def test_verify_refuses_free_text_extra_tags_and_bad_certs():
    z = _zebra()
    tags = attest_tags("worked", SHA, z["zebra"])

    def signed(tags, content):
        return sign_event(z["device"], ATTEST_KIND, tags, content)

    assert verify_attest(signed(tags, '{"reason":"run-succeeded"}'), [z["cert"]]).ok
    free = signed(tags, '{"reason":"Jane Doe asked about Canberra"}')
    assert verify_attest(free, [z["cert"]]).reason == "bad_reason"
    extra_key = signed(tags, '{"goal":"x","reason":"run-succeeded"}')
    assert verify_attest(extra_key, [z["cert"]]).reason == "malformed"
    extra_tag = signed([*tags, ["p", z["zebra"]]], '{"reason":"run-succeeded"}')
    assert verify_attest(extra_tag, [z["cert"]]).reason == "malformed"
    good = signed(tags, '{"reason":"run-succeeded"}')
    assert verify_attest(good, []).reason == "no_cert"
    tampered = Event(**{**good.to_dict(), "content": '{"reason":"run-failed"}'})
    assert verify_attest(tampered, [z["cert"]]).ok is False


# -- offer status transitions ----------------------------------------------------------------


async def test_offer_store_transitions():
    store = InMemoryOfferStore()
    record = OfferRecord(content_sha256=SHA, name="X", publisher_pubkey="p", event_id="e")
    assert await store.add(record) is True
    assert await store.add(record) is False  # one row per hash
    await store.set_status(SHA, JUDGING)
    await store.set_status(SHA, REJECTED, {"stage": "gym"})
    assert (await store.get(SHA)).judgement == {"stage": "gym"}
    await store.set_status(SHA, JUDGING)
    await store.set_status(SHA, ADOPTED)
    with pytest.raises(InvalidOfferTransition):
        await store.set_status(SHA, SEEN)
    assert (await store.get(SHA)).status == ADOPTED
    await store.set_status(SHA, DELISTED)
    with pytest.raises(InvalidOfferTransition):
        await store.set_status(SHA, JUDGING)
    with pytest.raises(KeyError):
        await store.set_status("0" * 64, JUDGING)


# -- offer intake ----------------------------------------------------------------------------


def _exchange(z: dict, relay: InMemoryRelay, operator: str | None = None) -> CommonsExchange:
    return CommonsExchange(publisher=_publisher(z, relay, operator), offers=InMemoryOfferStore())


async def _publish(relay: InMemoryRelay, *events: Event) -> None:
    client = InMemoryCommonsClient(relay)
    for e in events:
        await client.publish(e)


async def test_poll_stores_a_verified_offer_once(relay):
    a, b = _zebra(), _zebra()
    offer = _offer(a)
    await _publish(relay, a["cert"], offer)
    exchange = _exchange(b, relay)
    counts = await exchange.poll()
    assert counts["ok"] == 1
    [row] = await exchange.offers.list()
    assert (row.content_sha256, row.status, row.publisher_pubkey) == (SHA, SEEN, a["zebra"])
    assert row.name == "Capital Facts" and row.stats["runs"] == 5
    assert await exchange.mirror.get(offer.id) is not None
    assert await exchange.mirror.get(a["cert"].id) is not None  # the cert that attributed it

    # Duplicate: the same hash again (a re-signed offer) changes nothing
    again = build_offer(
        _content(),
        device_secret=a["device"],
        zebra_pubkey=a["zebra"],
        chain=[a["cert"]],
        created_at=offer.created_at + 5,
    )
    assert again.id != offer.id
    result = await exchange.intake(again, [a["cert"]])
    assert result.reason == "duplicate"
    assert [r.event_id for r in await exchange.offers.list()] == [offer.id]


async def test_intake_refuses_bad_signature_wrong_cert_and_tampered_yaml(relay):
    a, b, mallory = _zebra(), _zebra(), _zebra()
    exchange = _exchange(b, relay)
    offer = _offer(a)

    bad_sig = Event(**{**offer.to_dict(), "sig": "0" * 128})
    assert (await exchange.intake(bad_sig, [a["cert"]])).reason == "bad_signature"

    # Signed by Mallory's device but claiming Zebra A: no cert of A covers that device
    forged = build_offer(
        _content(),
        device_secret=mallory["device"],
        zebra_pubkey=mallory["zebra"],
        chain=[mallory["cert"]],
    )
    tags = [t if t[0] != "zebra" else ["zebra", a["zebra"]] for t in forged.tags]
    wrong = sign_event(mallory["device"], forged.kind, tags, forged.content)
    assert (await exchange.intake(wrong, [a["cert"], mallory["cert"]])).reason == "no_cert"

    # YAML changed after hashing: d no longer matches
    content = json.loads(offer.content)
    content["yaml"] = YAML.replace("Answer:", "Email jane@example.com:")
    tampered = sign_event(a["device"], offer.kind, offer.tags, json.dumps(content, sort_keys=True))
    assert (await exchange.intake(tampered, [a["cert"]])).reason == "hash_mismatch"

    assert await exchange.offers.list() == []
    assert await exchange.mirror.events() == []


async def test_own_offers_are_not_seen(relay):
    a = _zebra()
    await _publish(relay, a["cert"], _offer(a))
    exchange = _exchange(a, relay)
    assert (await exchange.poll()).get("ok") is None
    assert await exchange.offers.list() == []


async def test_revoked_device_delists_a_seen_offer(relay):
    a, b = _zebra(), _zebra()
    await _publish(relay, a["cert"], _offer(a))
    exchange = _exchange(b, relay)
    await exchange.poll()
    revoke = make_device_revoke(a["zebra_secret"], keys.public_key(a["device"]))
    await _publish(relay, revoke)
    counts = await exchange.poll()
    assert counts["delisted"] == 1
    assert (await exchange.offers.get(SHA)).status == DELISTED


async def test_poll_uses_receipts(relay):
    a, b = _zebra(), _zebra()
    operator = keys.generate_secret_key()
    offer = _offer(a)
    await _publish(relay, a["cert"], offer)
    await _publish(relay, make_receipt(operator, 7, offer.id, offer.kind))
    exchange = _exchange(b, relay, keys.public_key(operator))
    await exchange.poll()
    assert (await exchange.mirror.get(offer.id)).relay_seq == 7


# -- import input ----------------------------------------------------------------------------


def test_offer_as_export_reverifies_the_hash():
    a = _zebra()
    offer = _offer(a)
    verified = offer_as_export(offer_input(offer, [a["cert"]]))
    assert verified.ok and verified.content_sha256 == SHA
    assert verified.commons["foreign_users"] is False
    assert verified.commons["origin_pubkey"] == a["zebra"]
    assert verified.golden_tasks[0]["goal"] == GOLDEN[0]["goal"]
    content = json.loads(offer.content)
    content["yaml"] += "# changed\n  extra: 1\n"
    tampered = Event(**{**offer.to_dict(), "content": json.dumps(content)})
    assert offer_as_export(offer_input(tampered, [a["cert"]])).ok is False
    assert offer_as_export(offer_input(offer, [])).reason == "no_cert"
    assert offer_as_export("{}").reason == "wrong_format"
    assert offer_as_export(offer_input(offer, [a["cert"]]), expected_zebra="00" * 32).ok is False


# -- attesting and the hash-equality rule ----------------------------------------------------


def _adopted_library(tmp_path: Path, a: dict) -> WorkflowLibrary:
    library = WorkflowLibrary(tmp_path / "lib", owner_user_id=1)
    verified = offer_as_export(offer_input(_offer(a), [a["cert"]]))
    from zebra_agent.commons.export import adopt_export

    adopt_export(library, verified, name="Capital Facts (from A)")
    return library


async def test_after_run_attests_only_while_the_hash_equals_the_offer(tmp_path, relay):
    a, b = _zebra(), _zebra()
    await _publish(relay, a["cert"], _offer(a))
    exchange = _exchange(b, relay)
    await exchange.poll()
    library = _adopted_library(tmp_path, a)
    name = "Capital Facts (from A)"

    # Not adopted through this exchange (row still seen): nothing
    assert await exchange.after_run(library, name, True) is None
    await exchange.offers.set_status(SHA, JUDGING)
    await exchange.offers.set_status(SHA, ADOPTED)

    result = await exchange.after_run(library, name, True)
    assert result["label"] == "worked"
    result = await exchange.after_run(library, name, False)
    assert result["label"] == "failed"
    labels = [e.tag_values("l")[0] for e in relay.events if e.kind == ATTEST_KIND]
    assert labels == ["worked", "failed"]

    # A local change (hand edit keeping the block) gives a different hash: never attests
    path = next(library.library_path.glob("*.yaml"))
    path.write_text(path.read_text().replace("Answer: {{goal}}", "Reply: {{goal}}"))
    assert await exchange.after_run(library, name, True) is None
    assert len([e for e in relay.events if e.kind == ATTEST_KIND]) == 2

    # Unknown or not adopted workflows never attest
    assert await exchange.after_run(library, "No Such Workflow", True) is None


async def test_record_import_moves_the_row_and_attests(relay):
    a, b = _zebra(), _zebra()
    await _publish(relay, a["cert"], _offer(a))
    exchange = _exchange(b, relay)
    await exchange.poll()
    await exchange.offers.set_status(SHA, JUDGING)
    result = await exchange.record_import(
        SHA, status=REJECTED, label="rejected-gym", judgement={"stage": "gym"}
    )
    assert result["label"] == "rejected-gym"
    row = await exchange.offers.get(SHA)
    assert row.status == REJECTED and row.judgement == {"stage": "gym"}
    [event] = [e for e in relay.events if e.kind == ATTEST_KIND]
    assert verify_attest(event, [b["cert"]]).ok
    # A local outcome (owner said no) moves the row but publishes nothing
    await exchange.offers.set_status(SHA, JUDGING)
    assert await exchange.record_import(SHA, status=REJECTED, label=None) is None
    assert len([e for e in relay.events if e.kind == ATTEST_KIND]) == 1
    with pytest.raises(ValueError):
        await exchange.record_import(SHA, status=REJECTED, label="worked")


async def test_attestations_reach_the_publisher_view(relay):
    a, b, c = _zebra(), _zebra(), _zebra()
    offer_a = await _publisher(a, relay).publish_offer(_content(), None)
    assert offer_a["content_sha256"] == SHA
    exchange_a = CommonsExchange(publisher=_publisher(a, relay), offers=InMemoryOfferStore())
    await exchange_a.publisher.mirror.add(
        next(e for e in relay.events if e.id == offer_a["event_id"])
    )
    for z, label in ((b, "adopted"), (b, "worked"), (b, "failed"), (c, "rejected-ethics")):
        ex = _exchange(z, relay)
        await ex.attest(label, SHA)
    # Mallory's attestation with no cert on the relay is ignored
    m = _zebra()
    bogus = build_attest(
        "failed", SHA, device_secret=m["device"], zebra_pubkey=m["zebra"], chain=[m["cert"]]
    )
    await _publish(relay, bogus)
    kept = await exchange_a.fetch_attestations()
    assert kept == 4
    [mine] = await own_offers(exchange_a.mirror, a["zebra"])
    summary = mine["attestations"]
    counts = (summary["adopted"], summary["worked"], summary["failed"], summary["rejected"])
    assert counts == (1, 1, 1, 1)
    # The filter by #x finds them on the relay too
    found = await InMemoryCommonsClient(relay).fetch([Filter(kinds=(ATTEST_KIND,), hashes=(SHA,))])
    assert len(found) == 5


def test_attestation_summary_excludes_own():
    a, b = _zebra(), _zebra()
    events = [
        build_attest(
            lab, SHA, device_secret=z["device"], zebra_pubkey=z["zebra"], chain=[z["cert"]]
        )
        for z, lab in ((a, "worked"), (b, "adopted"), (b, "adopted"))
    ]
    summary = attestation_summary(events, exclude_zebra=a["zebra"])[SHA]
    assert summary["adopted"] == 1 and summary["worked"] == 0 and len(summary["items"]) == 2
