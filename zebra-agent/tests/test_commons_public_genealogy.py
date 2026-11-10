"""Public genealogy read model (#247): public events only, parents only between held offers."""

from __future__ import annotations

import json

import pytest

from zebra_agent.commons import keys
from zebra_agent.commons.attest import build_attest
from zebra_agent.commons.events import COMMONS_TAG, PROTOCOL_VERSION_TAG, sign_event
from zebra_agent.commons.identity import make_device_cert
from zebra_agent.commons.kinds import SKILL_KIND
from zebra_agent.commons.mirror import InMemoryCommonsMirror
from zebra_agent.commons.offer import build_offer, offer_content
from zebra_agent.commons.public_genealogy import (
    PUBLIC_GENEALOGY_KINDS,
    build_public_genealogy,
    public_events,
)
from zebra_agent.commons.trust import build_trust
from zebra_agent.provenance import content_sha256

YAML = """name: Capital Facts
version: 1
first_task: answer
tasks:
  answer:
    name: Answer
    action: llm_call
    properties:
      prompt: "Answer: {{goal}}"
"""
V2 = YAML.replace("Answer:", "Answer briefly:")
V3 = YAML.replace("Answer:", "Answer and cite:")
GOLDEN = [{"goal": "Capital of Australia?", "expected": "Canberra", "criteria": ["Canberra"]}]


def _zebra() -> dict:
    zebra_secret, device_secret = keys.generate_secret_key(), keys.generate_secret_key()
    cert = make_device_cert(
        zebra_secret, keys.public_key(device_secret), label="Home", sphere="home", observed=False
    )
    return {"zebra": keys.public_key(zebra_secret), "device": device_secret, "cert": cert}


def _offer(z: dict, yaml_text: str, *, parent: str | None = None, at: int = 1000):
    content = offer_content(
        name="Capital Facts",
        summary="Answers capital-city questions.",
        use_when="",
        stats={"runs": 6, "success_rate": 1.0, "avg_rating": 4.5, "gym_score": 0.9},
        actions=["llm_call"],
        golden_tasks=GOLDEN,
        yaml=yaml_text,
    )
    return build_offer(
        content,
        device_secret=z["device"],
        zebra_pubkey=z["zebra"],
        chain=[z["cert"]],
        parent=parent,
        created_at=at,
    )


def _attest(z: dict, label: str, sha: str, at: int = 2000):
    return build_attest(
        label,
        sha,
        device_secret=z["device"],
        zebra_pubkey=z["zebra"],
        chain=[z["cert"]],
        created_at=at,
    )


def _trust(z: dict, target: str, weight: float, reason: str, at: int = 3000):
    return build_trust(
        target,
        weight,
        reason,
        device_secret=z["device"],
        zebra_pubkey=z["zebra"],
        chain=[z["cert"]],
        created_at=at,
    )


@pytest.fixture
def a() -> dict:
    return _zebra()


@pytest.fixture
def b() -> dict:
    return _zebra()


def test_offers_linked_by_parent_with_publishers_and_attestations(a, b):
    sha1, sha2 = content_sha256(YAML), content_sha256(V2)
    events = [
        _offer(a, YAML, at=1000),
        _offer(b, V2, parent=sha1, at=1500),
        _attest(b, "adopted", sha1, at=1100),
        _attest(b, "worked", sha1, at=1200),
        _attest(b, "worked", sha1, at=1300),
        _attest(a, "rejected-gym", sha2, at=1600),
        a["cert"],
        b["cert"],
    ]
    g = build_public_genealogy(events, a["zebra"])
    assert [o.content_sha256 for o in g.offers] == [sha1, sha2]
    assert g.edges == [(sha1, sha2)]
    first, second = g.offers
    assert first.publisher == a["zebra"] and second.publisher == b["zebra"]
    assert (first.layer, second.layer) == (0, 1)
    assert first.children == [sha2] and second.parent == sha1
    assert first.attestations["adopted"] == 1 and first.attestations["worked"] == 2
    assert second.attestations["rejected"] == 1
    assert {i["reason"] for i in second.attestations["items"]} == {"golden-tasks-failed"}
    assert g.devices == {a["zebra"]: 1, b["zebra"]: 1}
    assert set(g.zebras) == {a["zebra"], b["zebra"]}


def test_a_parent_that_is_not_a_held_offer_is_never_named(a):
    private = "ab" * 32
    g = build_public_genealogy([_offer(a, V2, parent=private)], a["zebra"])
    [offer] = g.offers
    assert offer.parent is None and g.edges == []
    assert private not in json.dumps([o.__dict__ for o in g.offers], default=str)


def test_attestations_on_hashes_that_were_never_offered_are_ignored(a, b):
    private = "cd" * 32
    g = build_public_genealogy([_offer(a, YAML), _attest(b, "worked", private)], a["zebra"])
    assert private not in g.zebras and all(
        private not in json.dumps(o.attestations) for o in g.offers
    )


def test_only_public_kinds_are_read(a):
    skill = sign_event(a["device"], SKILL_KIND, [COMMONS_TAG, PROTOCOL_VERSION_TAG], "secret")
    events = [_offer(a, YAML), skill]
    assert public_events(events) == [events[0]]
    assert {k for k in PUBLIC_GENEALOGY_KINDS} == {30231, 1232, 30233, 30228}


def test_same_hash_offered_by_two_zebras_is_one_node(a, b):
    g = build_public_genealogy([_offer(a, YAML, at=1), _offer(b, YAML, at=2)], None)
    [offer] = g.offers
    assert offer.publishers == [a["zebra"], b["zebra"]] and offer.offered_at == 1


def test_latest_trust_per_pair_wins(a, b):
    c = _zebra()
    g = build_public_genealogy(
        [
            _trust(a, b["zebra"], 0.8, "vouched", at=10),
            _trust(a, b["zebra"], 0, "withdrawn", at=20),
            _trust(b, c["zebra"], 0.6, "experience", at=15),
        ],
        a["zebra"],
    )
    pairs = {(t.from_pubkey, t.to_pubkey): (t.weight, t.reason) for t in g.trust}
    assert pairs == {
        (a["zebra"], b["zebra"]): (0.0, "withdrawn"),
        (b["zebra"], c["zebra"]): (0.6, "experience"),
    }


def test_family_is_the_connected_lineage_only(a, b):
    sha1, sha2, sha3 = content_sha256(YAML), content_sha256(V2), content_sha256(V3)
    other = YAML.replace("Capital", "River")
    g = build_public_genealogy(
        [
            _offer(a, YAML, at=1),
            _offer(b, V2, parent=sha1, at=2),
            _offer(a, V3, parent=sha2, at=3),
            _offer(b, other, at=4),
        ],
        a["zebra"],
    )
    family = g.family(sha3)
    assert [o.content_sha256 for o in family.offers] == [sha1, sha2, sha3]
    assert [o.layer for o in family.offers] == [0, 1, 2]
    assert g.family("ef" * 32) is None


async def test_mirror_public_hashes_include_other_zebras_offers(a, b):
    mirror = InMemoryCommonsMirror()
    await mirror.add(_offer(a, YAML))
    await mirror.add(_offer(b, V2))
    await mirror.add(_trust(a, b["zebra"], 0.8, "vouched"))
    assert await mirror.public_hashes() == {content_sha256(YAML), content_sha256(V2)}
    assert await mirror.offered_hashes(a["zebra"]) == {content_sha256(YAML)}
