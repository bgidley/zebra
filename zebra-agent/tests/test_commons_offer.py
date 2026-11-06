"""OFFER events, the public hard filter, the local mirror and the publisher (#231, S4).

No network: relays are ``InMemoryRelay``s (``private=False`` for public ones).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from zebra_agent.commons import keys, kinds
from zebra_agent.commons.client import (
    Filter,
    InMemoryCommonsClient,
    InMemoryRelay,
    PublishRefused,
)
from zebra_agent.commons.events import COMMONS_TAG, PROTOCOL_VERSION_TAG, Event, sign_event
from zebra_agent.commons.identity import make_device_cert, make_device_revoke
from zebra_agent.commons.mirror import InMemoryCommonsMirror
from zebra_agent.commons.offer import (
    MIN_RUNS_TO_OFFER,
    OfferRefused,
    build_offer,
    offer_content,
    offer_stats,
    public_parent,
    verify_offer,
)
from zebra_agent.commons.publisher import CommonsPublisher
from zebra_agent.commons.receipts import make_receipt
from zebra_agent.metrics import WorkflowStats
from zebra_agent.provenance import content_sha256

REPO = Path(__file__).resolve().parents[2]
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


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def zebra():
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


def _content(yaml_text: str = YAML, **kw) -> dict:
    args = {
        "name": "Capital Facts",
        "summary": "Answers capital-city questions; 5 of 5 runs succeeded.",
        "use_when": "A question about a country's capital",
        "stats": offer_stats(WorkflowStats("Capital Facts", 5, 5, 4.5), 0.9),
        "actions": ["llm_call"],
        "golden_tasks": GOLDEN,
        "yaml": yaml_text,
    }
    return offer_content(**{**args, **kw})


def _offer(zebra, parent=None, content=None) -> Event:
    return build_offer(
        content or _content(),
        device_secret=zebra["device"],
        zebra_pubkey=zebra["zebra"],
        chain=[zebra["cert"]],
        parent=parent,
    )


# --- the kind table --------------------------------------------------------------------


def test_kind_numbers_are_fixed_and_public_list_excludes_private_kinds():
    assert kinds.OFFER_KIND == 30231 and 30000 <= kinds.OFFER_KIND < 40000
    assert kinds.TRUST_KIND == 30233 and kinds.ATTEST_KIND == 1232
    assert kinds.SKILL_KIND not in kinds.PUBLIC_KINDS
    assert kinds.WORKFLOW_EXPORT_KIND not in kinds.PUBLIC_KINDS
    all_kinds = [v for k, v in vars(kinds).items() if k.endswith("_KIND")]
    assert len(all_kinds) == len(set(all_kinds)) == len(kinds.KIND_NAMES)
    assert kinds.kind_name(kinds.OFFER_KIND) == "OFFER" and kinds.kind_name(1) == "kind 1"


@pytest.mark.parametrize("relay", ["sync-relay", "commons-relay"])
def test_relay_write_policies_use_the_same_kind_numbers(relay):
    policy = _load(REPO / "deploy" / "podman" / relay / "write_policy.py", f"wp_{relay}")
    for name, value in vars(policy).items():
        if name.endswith("_KIND"):
            assert getattr(kinds, name) == value, name
    if hasattr(policy, "PUBLIC_KINDS"):
        assert policy.PUBLIC_KINDS == kinds.PUBLIC_KINDS


# --- hard filter ------------------------------------------------------------------------


def _public() -> tuple[InMemoryRelay, InMemoryCommonsClient]:
    relay = InMemoryRelay(private=False)
    return relay, InMemoryCommonsClient(relay)


async def test_hard_filter_refuses_skill_and_unlisted_kinds_on_a_public_relay(zebra):
    relay, client = _public()
    tags = [["p", "aa" * 32], COMMONS_TAG, PROTOCOL_VERSION_TAG]
    skill = sign_event(zebra["device"], kinds.SKILL_KIND, tags, "ciphertext")
    export = sign_event(zebra["device"], kinds.WORKFLOW_EXPORT_KIND, tags, "{}")
    note = sign_event(zebra["device"], 1, tags, "hello")
    untagged = sign_event(zebra["device"], kinds.OFFER_KIND, [["d", "x"]], "{}")
    for event in (skill, export, note, untagged):
        with pytest.raises(PublishRefused):
            await client.publish(event)
    assert relay.events == []
    offer = _offer(zebra)
    await client.publish(offer)
    await client.publish(zebra["cert"])
    assert [e.id for e in relay.events] == [offer.id, zebra["cert"].id]


async def test_private_relay_still_takes_skill(zebra):
    relay = InMemoryRelay(private=True)
    skill = sign_event(zebra["device"], kinds.SKILL_KIND, [COMMONS_TAG], "ciphertext")
    await InMemoryCommonsClient(relay).publish(skill)
    assert relay.events == [skill]


# --- OFFER build / verify ---------------------------------------------------------------


def test_offer_round_trip_verifies_as_the_zebra(zebra):
    offer = _offer(zebra)
    digest = content_sha256(YAML)
    assert offer.kind == kinds.OFFER_KIND
    assert offer.tag_values("d") == offer.tag_values("x") == [digest]
    assert offer.tag_values("zebra") == [zebra["zebra"]]
    assert COMMONS_TAG in offer.tags and PROTOCOL_VERSION_TAG in offer.tags
    assert offer.pubkey == keys.public_key(zebra["device"])
    content = json.loads(offer.content)
    assert set(content) == {
        "name",
        "summary",
        "use_when",
        "stats",
        "actions",
        "golden_tasks",
        "yaml",
    }
    assert content["stats"] == {
        "runs": 5,
        "success_rate": 1.0,
        "avg_rating": 4.5,
        "gym_score": 0.9,
    }
    check = verify_offer(offer, [zebra["cert"]], expected_zebra=zebra["zebra"])
    assert check.ok and check.reason == "ok"
    assert check.zebra_pubkey == zebra["zebra"] and check.content_sha256 == digest


def test_tampered_or_unattributed_offer_fails(zebra):
    offer = _offer(zebra)
    content = json.loads(offer.content)
    content["yaml"] = YAML.replace("Answer:", "Reply:")
    resigned = sign_event(
        zebra["device"], offer.kind, offer.tags, json.dumps(content), offer.created_at
    )
    assert verify_offer(resigned, [zebra["cert"]]).reason == "hash_mismatch"
    summary_changed = {**json.loads(offer.content), "summary": "Always right."}
    forged = Event(**{**offer.to_dict(), "content": json.dumps(summary_changed)})
    assert verify_offer(forged, [zebra["cert"]]).reason == "bad_signature"
    assert verify_offer(offer, []).reason == "no_cert"
    other = keys.public_key(keys.generate_secret_key())
    assert verify_offer(offer, [zebra["cert"]], expected_zebra=other).reason == "wrong_zebra"
    revoke = make_device_revoke(zebra["zebra_secret"], keys.public_key(zebra["device"]))
    assert verify_offer(offer, [zebra["cert"], revoke]).reason == "revoked"


def test_build_refuses_an_uncertified_device(zebra):
    with pytest.raises(OfferRefused, match="not attributed"):
        build_offer(
            _content(), device_secret=zebra["device"], zebra_pubkey=zebra["zebra"], chain=[]
        )


@pytest.mark.parametrize(
    "golden,match",
    [([], "1-3 golden tasks"), (GOLDEN * 4, "1-3 golden tasks"), ([{"goal": "x"}], "criteria")],
)
def test_offer_content_needs_one_to_three_golden_tasks(golden, match):
    with pytest.raises(OfferRefused, match=match):
        _content(golden_tasks=golden)


# --- parent privacy -----------------------------------------------------------------------


def test_private_parent_is_never_named(zebra):
    private_parent = "ab" * 32
    block = {"parent_sha256": private_parent, "ancestors": [private_parent, "cd" * 32]}
    assert public_parent(block, offered=set()) is None
    offer = _offer(zebra, parent=public_parent(block, set()))
    assert offer.tag_values("parent") == []
    text = json.dumps(offer.to_dict())
    assert private_parent not in text and "cd" * 32 not in text


async def test_publicly_offered_parent_is_named(zebra):
    publisher, relay, _mirrors = _publisher(zebra)
    first = await publisher.publish_offer(_content(), {"content_sha256": content_sha256(YAML)})
    v2 = YAML.replace("Answer:", "Answer briefly:")
    block = {"content_sha256": content_sha256(v2), "parent_sha256": first["content_sha256"]}
    second = await publisher.publish_offer(_content(yaml_text=v2), block)
    assert second["parent"] == first["content_sha256"]
    [offer2] = [e for e in relay.events if e.id == second["event_id"]]
    assert offer2.tag_values("parent") == [first["content_sha256"]]
    assert verify_offer(offer2, [zebra["cert"]]).parent == first["content_sha256"]


# --- mirror -------------------------------------------------------------------------------


async def test_in_memory_mirror_is_append_only_and_finds_offered_hashes(zebra):
    mirror = InMemoryCommonsMirror()
    offer = _offer(zebra)
    assert await mirror.add(offer) is True
    assert await mirror.add(offer, relay_seq=9) is False  # stored once, never changed
    assert (await mirror.get(offer.id)).relay_seq is None
    assert await mirror.offered_hashes(zebra["zebra"]) == {content_sha256(YAML)}
    assert await mirror.offered_hashes("ff" * 32) == set()


# --- publisher ----------------------------------------------------------------------------


def _publisher(zebra, *, operator=None, mirrors=0, observed=False, certs=None):
    relay = InMemoryRelay(private=False)
    mirror_relays = [InMemoryRelay(private=False) for _ in range(mirrors)]
    publisher = CommonsPublisher(
        canonical=InMemoryCommonsClient(relay),
        mirrors=[InMemoryCommonsClient(r) for r in mirror_relays],
        device_secret=zebra["device"],
        zebra_pubkey=zebra["zebra"],
        mirror=InMemoryCommonsMirror(),
        certs=certs or [zebra["cert"]],
        sphere="home",
        observed=observed,
        receipt_pubkey=keys.public_key(operator) if operator else None,
        receipt_wait=0,
    )
    return publisher, relay, mirror_relays


def test_publisher_refuses_a_private_client(zebra):
    with pytest.raises(ValueError, match="public"):
        CommonsPublisher(
            canonical=InMemoryCommonsClient(InMemoryRelay(private=True)),
            device_secret=zebra["device"],
            zebra_pubkey=zebra["zebra"],
            mirror=InMemoryCommonsMirror(),
        )


async def test_publish_puts_cert_then_offer_on_canonical_and_mirrors_and_records_them(zebra):
    work_secret = keys.generate_secret_key()
    work_cert = make_device_cert(
        zebra["zebra_secret"], keys.public_key(work_secret), label="Work", sphere="work",
        observed=True,
    )  # fmt: skip
    publisher, relay, [mirror_relay] = _publisher(
        zebra, mirrors=1, certs=[zebra["cert"], work_cert]
    )
    result = await publisher.publish_offer(_content(), {"content_sha256": content_sha256(YAML)})
    # Only the signing device's cert goes public, never the work laptop's.
    assert [e.kind for e in relay.events] == [kinds.DEVICE_CERT_KIND, kinds.OFFER_KIND]
    assert relay.events[0].id == zebra["cert"].id
    assert [e.id for e in mirror_relay.events] == [e.id for e in relay.events]
    assert list(result["mirrors"].values()) == ["ok"]
    rows = await publisher.mirror.events()
    assert [m.event.id for m in rows] == [e.id for e in relay.events]
    assert result["receipt_seq"] is None  # no operator configured


async def test_publish_records_the_operator_receipt(zebra):
    operator = keys.generate_secret_key()
    publisher, relay, _ = _publisher(zebra, operator=operator)
    stranger = keys.generate_secret_key()
    offer = await publisher.build(_content(), {})
    relay.store(make_receipt(stranger, 1, offer.id, offer.kind))  # forged: not the operator
    relay.store(make_receipt(operator, 7, offer.id, offer.kind))
    result = await publisher.publish_offer(_content(), {})
    assert result["event_id"] == offer.id and result["receipt_seq"] == 7
    stored = await publisher.mirror.events(kind=kinds.RECEIPT_KIND)
    assert [m.event.pubkey for m in stored] == [keys.public_key(operator)]


async def test_refresh_receipts_picks_up_late_receipts(zebra):
    operator = keys.generate_secret_key()
    publisher, relay, _ = _publisher(zebra, operator=operator)
    result = await publisher.publish_offer(_content(), {})
    assert result["receipt_seq"] is None
    relay.store(make_receipt(operator, 3, result["event_id"], kinds.OFFER_KIND))
    assert await publisher.refresh_receipts() == 1
    seq = await publisher.mirror.receipt_seq(keys.public_key(operator))
    assert seq[result["event_id"]] == 3
    receipts = await publisher.canonical.fetch([Filter(kinds=(kinds.RECEIPT_KIND,))])
    assert len(receipts) == 1


async def test_a_failing_mirror_does_not_stop_the_offer(zebra):
    publisher, relay, _ = _publisher(zebra)

    class Down(InMemoryCommonsClient):
        async def publish(self, event):
            raise ConnectionError("mirror down")

    publisher.mirrors = [Down(InMemoryRelay(private=False))]
    result = await publisher.publish_offer(_content(), {})
    assert "mirror down" in next(iter(result["mirrors"].values()))
    assert relay.events[-1].id == result["event_id"]


def test_observed_taint_counts_unknown_spheres(zebra):
    work = keys.generate_secret_key()
    work_cert = make_device_cert(
        zebra["zebra_secret"], keys.public_key(work), label="W", sphere="work", observed=True
    )
    publisher, _, _ = _publisher(zebra, certs=[zebra["cert"], work_cert])
    assert publisher.observed_taint({"tainted_by": ["home"]}) == []
    assert publisher.observed_taint({"tainted_by": ["home", "work"]}) == ["work"]
    assert publisher.observed_taint({"tainted_by": ["mystery"]}) == ["mystery"]
    assert MIN_RUNS_TO_OFFER == 5
