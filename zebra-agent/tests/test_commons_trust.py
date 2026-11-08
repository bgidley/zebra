"""The web of trust (#233, S6): TRUST events, local trust, experience, import score.

Pure functions first (``commons/trust.py``), then ``WebOfTrust`` over the in-memory store, then
several Zebras over an in-memory public relay: the owner vouches A, A trusts B, and B's trust
arrives with its path; an offer from an unconnected Zebra scores 0.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from zebra_agent.commons import keys
from zebra_agent.commons.attest import (
    ADOPTED,
    FAILED,
    PII_FOUND,
    REJECTED_ETHICS,
    REJECTED_GYM,
    REJECTED_PII,
    WORKED,
)
from zebra_agent.commons.client import InMemoryCommonsClient, InMemoryRelay
from zebra_agent.commons.events import sign_event
from zebra_agent.commons.exchange import CommonsExchange
from zebra_agent.commons.identity import make_device_cert, make_device_revoke
from zebra_agent.commons.kinds import ATTEST_KIND, TRUST_KIND
from zebra_agent.commons.mirror import InMemoryCommonsMirror
from zebra_agent.commons.offers import InMemoryOfferStore, OfferRecord
from zebra_agent.commons.peers import InMemoryTrustStore, PeerRecord, TrustEdge, is_newer
from zebra_agent.commons.publisher import CommonsPublisher
from zebra_agent.commons.trust import (
    DECAY,
    IMPORT_SCORE_THRESHOLD,
    MAX_HOPS,
    VOUCH_WEIGHT,
    TrustPath,
    TrustRefused,
    attestation_signal,
    build_trust,
    clears_threshold,
    compute_trust,
    experience_update,
    import_score,
    path_text,
    should_publish,
    trust_content,
    trust_tags,
    verify_trust,
)
from zebra_agent.commons.web_of_trust import WebOfTrust, offer_score

ME, A, B, C, D, S1, S2 = (f"{i:064x}" for i in range(1, 8))


def _zebra() -> dict:
    zebra_secret, device_secret = keys.generate_secret_key(), keys.generate_secret_key()
    cert = make_device_cert(
        zebra_secret, keys.public_key(device_secret), label="Home", sphere="home", observed=False
    )
    return {
        "secret": zebra_secret,
        "zebra": keys.public_key(zebra_secret),
        "device": device_secret,
        "cert": cert,
    }


def _publisher(z: dict, relay: InMemoryRelay) -> CommonsPublisher:
    return CommonsPublisher(
        canonical=InMemoryCommonsClient(relay),
        device_secret=z["device"],
        zebra_pubkey=z["zebra"],
        mirror=InMemoryCommonsMirror(),
        certs=[z["cert"]],
        receipt_wait=0,
    )


# -- local trust -----------------------------------------------------------------------------


def test_vouched_seed_direct_is_its_weight():
    paths = compute_trust(ME, {(ME, A): 0.8}, seeds={A})
    assert paths[A].value == pytest.approx(0.8)
    assert paths[A].nodes == [ME, A]


def test_two_hops_is_product_with_one_decay():
    paths = compute_trust(ME, {(ME, A): 0.8, (A, B): 0.6}, seeds={A})
    assert 0.8 * 0.6 == pytest.approx(0.48)
    assert paths[B].value == pytest.approx(0.8 * 0.6 * DECAY) == pytest.approx(0.432)
    assert paths[B].hops == ((ME, A, 0.8), (A, B, 0.6))


def test_three_hops_decays_twice():
    paths = compute_trust(ME, {(ME, A): 0.8, (A, B): 0.6, (B, C): 0.5}, seeds={A})
    assert paths[C].value == pytest.approx(0.8 * 0.6 * 0.5 * 0.81)
    assert round(paths[C].value, 3) == 0.194


def test_path_length_is_capped():
    edges = {(ME, A): 0.9, (A, B): 0.9, (B, C): 0.9, (C, D): 0.9}
    paths = compute_trust(ME, edges, seeds={A})
    assert MAX_HOPS == 3
    assert C in paths and D not in paths


def test_max_over_paths():
    edges = {(ME, A): 0.8, (ME, S1): 0.8, (A, B): 0.3, (S1, B): 0.9}
    paths = compute_trust(ME, edges, seeds={A, S1})
    assert paths[B].value == pytest.approx(0.8 * 0.9 * DECAY)
    assert paths[B].nodes == [ME, S1, B]


def test_longer_path_wins_when_stronger():
    edges = {(ME, A): 0.8, (A, B): 0.2, (A, C): 1.0, (C, B): 1.0}
    paths = compute_trust(ME, edges, seeds={A})
    assert paths[B].value == pytest.approx(0.8 * 1.0 * 1.0 * DECAY**2)


def test_negative_edges_are_not_propagated_past_one_hop():
    edges = {(ME, A): 0.8, (A, B): -0.5, (B, C): 0.9}
    paths = compute_trust(ME, edges, seeds={A})
    assert paths[B].value == pytest.approx(0.8 * -0.5 * DECAY)
    assert C not in paths


def test_own_negative_edge_wins_over_a_friend():
    edges = {(ME, A): 0.8, (A, B): 0.9, (ME, B): -0.8}
    paths = compute_trust(ME, edges, seeds={A})
    assert paths[B].value == pytest.approx(-0.8)


def test_sybil_cluster_without_a_seed_path_is_zero():
    edges = {(ME, A): 0.8, (S1, S2): 1.0, (S2, S1): 1.0, (S1, B): 1.0, (S2, B): 1.0}
    paths = compute_trust(ME, edges, seeds={A})
    assert S1 not in paths and S2 not in paths and B not in paths


def test_direct_experience_edge_needs_an_anchor():
    """My own positive edge to a Zebra no seed reaches does not start a path (Sybil limit)."""
    assert compute_trust(ME, {(ME, B): 0.9}, seeds=set()) == {}
    paths = compute_trust(ME, {(ME, A): 0.8, (A, B): 0.1, (ME, B): 0.9}, seeds={A})
    assert paths[B].value == pytest.approx(0.9)


def test_unvouched_direct_edge_is_not_a_seed():
    paths = compute_trust(ME, {(ME, A): 0.8, (A, B): 0.6}, seeds=set())
    assert paths == {}


def test_computation_is_deterministic():
    edges = {(ME, A): 0.8, (ME, S1): 0.8, (A, B): 0.5, (S1, B): 0.5}
    first = compute_trust(ME, edges, seeds={A, S1})
    again = compute_trust(ME, dict(reversed(list(edges.items()))), seeds={S1, A})
    assert first == again
    assert first[B].nodes == [ME, A, B]  # tie: the smaller path


def test_path_text():
    paths = compute_trust(ME, {(ME, A): 0.8, (A, B): 0.6}, seeds={A})
    names = {A: "A", B: "B"}
    assert path_text(paths[B], names.get) == "B via A: 0.8 × 0.6 × 0.9 = 0.43"
    assert path_text(paths[A], names.get) == "A directly: 0.8 = 0.80"
    assert path_text(TrustPath(0.0), names.get).startswith("no path")
    assert TrustPath.from_dict(paths[B].to_dict()) == paths[B]


# -- TRUST events ----------------------------------------------------------------------------


def test_build_and_verify_trust():
    z, target = _zebra(), _zebra()["zebra"]
    event = build_trust(
        target,
        0.6,
        "vouched",
        device_secret=z["device"],
        zebra_pubkey=z["zebra"],
        chain=[z["cert"]],
    )
    assert event.kind == TRUST_KIND == 30233
    assert event.tags == trust_tags(target, z["zebra"])
    assert json.loads(event.content) == {"reason": "vouched", "weight": 0.6}
    check = verify_trust(event, [z["cert"]])
    assert check.ok, check.reason
    assert (check.from_pubkey, check.to_pubkey, check.weight) == (z["zebra"], target, 0.6)


def test_owner_note_is_a_reason():
    z, target = _zebra(), _zebra()["zebra"]
    event = build_trust(
        target,
        0.8,
        "Met at the meetup",
        device_secret=z["device"],
        zebra_pubkey=z["zebra"],
        chain=[z["cert"]],
    )
    assert verify_trust(event, [z["cert"]]).trust_reason == "Met at the meetup"
    for bad in ("", "x" * 141, "two\nlines"):
        with pytest.raises(TrustRefused):
            trust_content(0.5, bad)


@pytest.mark.parametrize("weight", [1.5, -1.01, float("nan"), True, "0.5"])
def test_build_refuses_bad_weight(weight):
    z = _zebra()
    with pytest.raises(TrustRefused):
        build_trust(
            _zebra()["zebra"],
            weight,
            "vouched",
            device_secret=z["device"],
            zebra_pubkey=z["zebra"],
            chain=[z["cert"]],
        )


def test_build_refuses_self_and_uncertified_device():
    z = _zebra()
    with pytest.raises(TrustRefused):
        build_trust(
            z["zebra"], 0.5, "vouched", device_secret=z["device"], zebra_pubkey=z["zebra"],
            chain=[z["cert"]],
        )  # fmt: skip
    with pytest.raises(TrustRefused):
        build_trust(
            _zebra()["zebra"], 0.5, "vouched", device_secret=keys.generate_secret_key(),
            zebra_pubkey=z["zebra"], chain=[z["cert"]],
        )  # fmt: skip


def _forge(z: dict, tags, content) -> object:
    return sign_event(z["device"], TRUST_KIND, tags, content)


def test_verify_refuses_tampering_and_wrong_shapes():
    z, target = _zebra(), _zebra()["zebra"]
    good = trust_content(0.5, "vouched")
    tags = trust_tags(target, z["zebra"])
    cases = {
        "bad_weight": _forge(z, tags, json.dumps({"reason": "vouched", "weight": 2})),
        "bad_reason": _forge(z, tags, json.dumps({"reason": "", "weight": 0.5})),
        "malformed": _forge(z, [*tags, ["e", "x"]], good),
    }
    for reason, event in cases.items():
        assert verify_trust(event, [z["cert"]]).reason == reason
    extra = _forge(z, tags, json.dumps({"reason": "vouched", "weight": 0.5, "x": 1}))
    assert verify_trust(extra, [z["cert"]]).reason == "malformed"
    other = _forge(z, [["d", target], ["p", z["zebra"]], *tags[2:]], good)
    assert verify_trust(other, [z["cert"]]).reason == "malformed"
    selfish = _forge(z, trust_tags(z["zebra"], z["zebra"]), good)
    assert verify_trust(selfish, [z["cert"]]).reason == "self"
    attest_kind = sign_event(z["device"], ATTEST_KIND, tags, good)
    assert verify_trust(attest_kind, [z["cert"]]).reason == "wrong_kind"

    event = build_trust(
        target, 0.5, "vouched", device_secret=z["device"], zebra_pubkey=z["zebra"],
        chain=[z["cert"]],
    )  # fmt: skip
    tampered = type(event)(**{**event.to_dict(), "content": trust_content(0.9, "vouched")})
    assert verify_trust(tampered, [z["cert"]]).reason == "bad_signature"
    assert verify_trust(event, []).reason == "no_cert"
    revoke = make_device_revoke(z["secret"], keys.public_key(z["device"]))
    assert verify_trust(event, [z["cert"], revoke]).reason == "revoked"


# -- latest wins -----------------------------------------------------------------------------


def test_edge_latest_wins_by_receipt_then_created_at():
    old = TrustEdge(A, B, 0.2, "experience", "a" * 64, created_at=100, relay_seq=5)
    new = TrustEdge(A, B, 0.6, "experience", "b" * 64, created_at=50, relay_seq=6)
    assert is_newer(new, old)  # receipt order beats a backdated created_at
    assert not is_newer(old, new)
    no_seq = TrustEdge(A, B, 0.6, "experience", "c" * 64, created_at=200)
    assert is_newer(no_seq, old) and not is_newer(old, no_seq)
    assert not is_newer(old, old)


async def test_store_keeps_latest_edge():
    store = InMemoryTrustStore()
    newer = TrustEdge(A, B, 0.6, "vouched", "b" * 64, created_at=200)
    older = TrustEdge(A, B, 0.1, "vouched", "a" * 64, created_at=100)
    assert await store.put_if_newer(newer)
    assert not await store.put_if_newer(older)
    assert (await store.get_edge(A, B)).weight == 0.6


# -- experience ------------------------------------------------------------------------------


def test_experience_ewma():
    assert experience_update(None, WORKED) == pytest.approx(0.2)
    assert experience_update(0.5, WORKED) == pytest.approx(0.6)
    assert experience_update(0.5, FAILED) == pytest.approx(0.2)
    for label in (REJECTED_ETHICS, REJECTED_GYM, PII_FOUND):
        assert experience_update(0.0, label) == pytest.approx(-0.2)
    assert experience_update(0.5, ADOPTED) is None
    assert experience_update(0.5, REJECTED_PII) is None


def test_vouch_is_a_floor_and_distrust_a_ceiling():
    weight = VOUCH_WEIGHT
    for _ in range(20):
        weight = experience_update(weight, FAILED, owner_weight=VOUCH_WEIGHT)
    assert weight == pytest.approx(VOUCH_WEIGHT)
    assert experience_update(0.8, WORKED, owner_weight=0.8) == pytest.approx(0.84)
    assert experience_update(-0.8, WORKED, owner_weight=-0.8) == pytest.approx(-0.8)


def test_publish_threshold():
    assert should_publish(0.2, None)
    assert not should_publish(0.84, 0.8)
    assert should_publish(0.9, 0.8)


# -- import score ----------------------------------------------------------------------------


def test_attestation_signal_is_trust_weighted():
    trust = {A: 0.8, B: 0.2, S1: 0.0}
    reports = [(A, WORKED), (B, FAILED), (S1, FAILED), (S1, FAILED), (A, ADOPTED)]
    assert attestation_signal(reports, trust) == pytest.approx((0.8 - 0.2) / 1.0)
    assert attestation_signal(reports, trust, exclude={A}) == pytest.approx(-1.0)
    assert attestation_signal([(S1, WORKED)], trust) == 0.0


def test_import_score_and_threshold():
    assert import_score(0.8, 0.5) == pytest.approx(0.7 * 0.8 + 0.3 * 0.5)
    assert import_score(0.0, 0.0) == 0.0
    assert IMPORT_SCORE_THRESHOLD == 0.5
    assert clears_threshold(0.5) and not clears_threshold(0.4999)
    assert clears_threshold(import_score(5 / 7, 0.0))


def test_offer_score_excludes_publisher_and_self():
    trust = {A: 0.8, B: 0.6}
    reports = [(A, WORKED), (B, WORKED), (ME, FAILED)]
    score = offer_score(A, reports, trust, ME)
    assert score["signal"] == pytest.approx(1.0)  # only B counts
    assert score["score"] == pytest.approx(0.7 * 0.8 + 0.3)
    assert score["clears"]
    unknown = offer_score(S1, [(S2, WORKED)], trust, ME)
    assert unknown == {"score": 0.0, "local_trust": 0.0, "signal": 0.0, "clears": False}


# -- WebOfTrust ------------------------------------------------------------------------------


async def test_vouch_without_publishing_is_local_only():
    wot = WebOfTrust(InMemoryTrustStore(), ME)
    result = await wot.vouch(A, display_name="Alice's Zebra")
    assert result["published"] is False
    peer = await wot.store.get_peer(A)
    assert peer.vouched_by_user and peer.display_name == "Alice's Zebra"
    assert peer.local_trust == pytest.approx(VOUCH_WEIGHT)
    edge = await wot.store.get_edge(ME, A)
    assert edge.weight == VOUCH_WEIGHT and edge.event_id == "" and edge.published_weight is None
    assert await wot.publish_pending() == 0


async def test_withdraw_and_distrust():
    wot = WebOfTrust(InMemoryTrustStore(), ME)
    await wot.vouch(A)
    await wot.store.save_edge(TrustEdge(A, B, 0.6, "vouched", "e" * 64, created_at=1))
    await wot.recompute()
    assert (await wot.store.get_peer(B)).local_trust == pytest.approx(0.432)
    await wot.withdraw(A)
    assert not (await wot.store.get_peer(A)).vouched_by_user
    assert (await wot.store.get_peer(B)).local_trust == 0.0
    await wot.distrust(A, note="Spams the relay")
    peer = await wot.store.get_peer(A)
    assert peer.local_trust == pytest.approx(-0.8) and peer.owner_weight == -0.8
    assert (await wot.store.get_edge(ME, A)).reason == "Spams the relay"
    with pytest.raises(TrustRefused):
        await wot.vouch(ME)
    with pytest.raises(TrustRefused):
        await wot.vouch("not-a-key")


async def test_experience_moves_own_edge_and_respects_the_vouch():
    relay = InMemoryRelay(private=False)
    me, other = _zebra(), _zebra()
    publisher = _publisher(me, relay)
    wot = WebOfTrust(InMemoryTrustStore(), me["zebra"], publisher=publisher)
    first = await wot.record_experience(other["zebra"], WORKED)
    assert first == {"weight": pytest.approx(0.2), "published": True}
    second = await wot.record_experience(other["zebra"], WORKED)
    assert second == {"weight": pytest.approx(0.36), "published": True}  # moved 0.16
    assert len([e for e in relay.events if e.kind == TRUST_KIND]) == 2
    assert await wot.record_experience(other["zebra"], ADOPTED) is None
    assert await wot.record_experience(me["zebra"], WORKED) is None

    await wot.vouch(other["zebra"])
    for _ in range(10):
        await wot.record_experience(other["zebra"], FAILED)
    edge = await wot.store.get_edge(me["zebra"], other["zebra"])
    assert edge.weight == pytest.approx(VOUCH_WEIGHT)
    assert edge.reason == "vouched"
    latest = max((e for e in relay.events if e.kind == TRUST_KIND), key=lambda e: e.created_at)
    assert json.loads(latest.content)["weight"] == VOUCH_WEIGHT


async def test_publish_threshold_avoids_spam():
    relay = InMemoryRelay(private=False)
    me, other = _zebra(), _zebra()
    wot = WebOfTrust(InMemoryTrustStore(), me["zebra"], publisher=_publisher(me, relay))
    await wot.vouch(other["zebra"])
    count = len([e for e in relay.events if e.kind == TRUST_KIND])
    await wot.record_experience(other["zebra"], WORKED)  # 0.84: below the threshold
    assert len([e for e in relay.events if e.kind == TRUST_KIND]) == count
    edge = await wot.store.get_edge(me["zebra"], other["zebra"])
    assert edge.weight == pytest.approx(0.84) and edge.published_weight == 0.8
    await wot.record_experience(other["zebra"], WORKED)  # 0.872
    await wot.record_experience(other["zebra"], WORKED)  # 0.898: 0.1 above 0.8
    assert len([e for e in relay.events if e.kind == TRUST_KIND]) == count + 1


class _DownClient(InMemoryCommonsClient):
    async def publish(self, event):
        raise ConnectionError("relay down")


async def test_failed_publish_is_retried():
    relay = InMemoryRelay(private=False)
    me, other = _zebra(), _zebra()
    publisher = _publisher(me, relay)
    publisher.canonical = _DownClient(relay)
    wot = WebOfTrust(InMemoryTrustStore(), me["zebra"], publisher=publisher)
    assert (await wot.vouch(other["zebra"]))["published"] is False
    publisher.canonical = InMemoryCommonsClient(relay)
    assert await wot.publish_pending() == 1
    assert await wot.publish_pending() == 0
    [event] = [e for e in relay.events if e.kind == TRUST_KIND]
    assert verify_trust(event, [me["cert"]]).to_pubkey == other["zebra"]


class _PausingStore(InMemoryTrustStore):
    """Pauses the next ``list_peers`` after taking its snapshot until ``go`` is set, so a
    recompute holds a stale copy of every peer while the owner acts (#233 review)."""

    def __init__(self) -> None:
        super().__init__()
        self.armed = False
        self.paused = asyncio.Event()
        self.go = asyncio.Event()

    async def list_peers(self):
        snapshot = await super().list_peers()
        if self.armed:
            self.armed = False
            self.paused.set()
            await self.go.wait()
        return snapshot


async def test_recompute_never_undoes_a_distrust_made_meanwhile():
    """The owner distrusts X while a recompute holds X as vouched: the distrust stays, and the
    next experience cannot lift the edge above it."""
    store = _PausingStore()
    tick = WebOfTrust(store, ME)  # e.g. the daemon's
    owner = WebOfTrust(store, ME)  # e.g. a request's: only the store is shared
    await owner.vouch(A)
    store.armed = True
    recompute = asyncio.create_task(tick.recompute())
    await store.paused.wait()  # the recompute holds the vouched peer
    await owner.distrust(A)
    store.go.set()
    await recompute
    peer = await store.get_peer(A)
    assert peer.owner_weight == -0.8 and not peer.vouched_by_user
    await tick.recompute()
    assert (await store.get_peer(A)).local_trust == pytest.approx(-0.8)
    await tick.record_experience(A, WORKED)
    assert (await store.get_edge(ME, A)).weight == pytest.approx(-0.8)


async def test_shared_web_of_trust_serialises_owner_and_tick():
    """One shared ``WebOfTrust`` (publishing on): a vouch made during a tick's recompute waits
    for it, so the vouched peer ends with its trust, not the tick's stale 0."""
    store = _PausingStore()
    wot = WebOfTrust(store, ME)
    await store.touch_peer(A)
    store.armed = True
    recompute = asyncio.create_task(wot.recompute())
    await store.paused.wait()
    vouch = asyncio.create_task(wot.vouch(A))
    await asyncio.sleep(0)
    assert not vouch.done()  # waits for the lock
    store.go.set()
    await recompute
    await vouch
    peer = await store.get_peer(A)
    assert peer.vouched_by_user and peer.local_trust == pytest.approx(VOUCH_WEIGHT)


async def test_touch_peer_keeps_owner_fields():
    store = InMemoryTrustStore()
    await store.set_owner_fields(A, vouched_by_user=True, owner_weight=0.8, display_name="A")
    await store.set_computed(A, 0.8, {"value": 0.8})
    peer = await store.touch_peer(A, 50)
    assert peer.vouched_by_user and peer.owner_weight == 0.8 and peer.display_name == "A"
    assert peer.local_trust == 0.8 and peer.last_seen == 50


@pytest.mark.parametrize(
    "published, action, expected",
    [(0.75, "vouch", VOUCH_WEIGHT), (0.05, "withdraw", 0.0), (-0.75, "distrust", -0.8)],
)
async def test_owner_change_is_retried_below_the_experience_threshold(published, action, expected):
    """An owner change the relay missed is retried even when it is within 0.1 of the weight
    last published (the threshold only throttles experience)."""
    relay = InMemoryRelay(private=False)
    me, other = _zebra(), _zebra()
    publisher = _publisher(me, relay)
    wot = WebOfTrust(InMemoryTrustStore(), me["zebra"], publisher=publisher)
    x = other["zebra"]
    await wot.store.save_edge(
        TrustEdge(me["zebra"], x, published, "experience", "e" * 64, 1, published_weight=published)
    )
    publisher.canonical = _DownClient(relay)
    owner_action = {"vouch": wot.vouch, "withdraw": wot.withdraw, "distrust": wot.distrust}
    assert (await owner_action[action](x))["published"] is False
    assert (await wot.store.get_edge(me["zebra"], x)).pending
    publisher.canonical = InMemoryCommonsClient(relay)
    assert await wot.publish_pending() == 1
    edge = await wot.store.get_edge(me["zebra"], x)
    assert not edge.pending and edge.published_weight == expected
    [event] = [e for e in relay.events if e.kind == TRUST_KIND]
    assert json.loads(event.content)["weight"] == expected
    assert await wot.publish_pending() == 0


async def test_experience_keeps_an_unpublished_owner_change_pending():
    relay = InMemoryRelay(private=False)
    me, other = _zebra(), _zebra()
    publisher = _publisher(me, relay)
    publisher.canonical = _DownClient(relay)
    wot = WebOfTrust(InMemoryTrustStore(), me["zebra"], publisher=publisher)
    await wot.vouch(other["zebra"])
    await wot.record_experience(other["zebra"], WORKED)
    assert (await wot.store.get_edge(me["zebra"], other["zebra"])).pending


async def test_superseded_publish_does_not_overwrite_the_newer_change():
    store = InMemoryTrustStore()
    first = TrustEdge(ME, A, 0.8, "vouched", created_at=10, pending=True)
    await store.save_edge(first)
    await store.save_edge(TrustEdge(ME, A, -0.8, "distrusted", created_at=11, pending=True))
    recorded = await store.mark_published(
        first, event_id="e" * 64, created_at=10, relay_seq=None, published_weight=0.8
    )
    assert not recorded
    edge = await store.get_edge(ME, A)
    assert edge.weight == -0.8 and edge.pending and edge.published_weight is None


# -- several Zebras over one relay -----------------------------------------------------------


def _exchange(z: dict, relay: InMemoryRelay) -> CommonsExchange:
    publisher = _publisher(z, relay)
    return CommonsExchange(
        publisher=publisher,
        offers=InMemoryOfferStore(),
        trust=WebOfTrust(InMemoryTrustStore(), z["zebra"], publisher=publisher),
    )


async def test_owner_vouches_a_and_a_trusts_b():
    """The E2E of #233: my owner vouches A; A's owner vouches B; I learn B with its path."""
    relay = InMemoryRelay(private=False)
    me, a, b, sybil, sybil2 = (_zebra() for _ in range(5))
    mine, theirs = _exchange(me, relay), _exchange(a, relay)
    sybils = [_exchange(sybil, relay), _exchange(sybil2, relay)]

    await theirs.trust.vouch(b["zebra"])  # A's owner knows B (0.8)
    await theirs.trust.distrust(sybil["zebra"])
    await sybils[0].trust.vouch(sybil2["zebra"])  # a Sybil ring vouching for itself
    await sybils[1].trust.vouch(sybil["zebra"])
    await sybils[1].trust.vouch(b["zebra"])
    await mine.trust.vouch(a["zebra"], display_name="A")

    counts = await mine.poll()
    assert counts["trust"] >= 4
    trust = await mine.trust.trust_map()
    assert trust[a["zebra"]] == pytest.approx(0.8)
    assert trust[b["zebra"]] == pytest.approx(0.8 * 0.8 * DECAY)
    assert trust[sybil["zebra"]] == pytest.approx(0.8 * -0.8 * DECAY)
    assert trust[sybil2["zebra"]] == 0.0  # only a distrusted Zebra trusts it
    peer = await mine.trust.store.get_peer(b["zebra"])
    path = TrustPath.from_dict(peer.best_path)
    assert path.nodes == [me["zebra"], a["zebra"], b["zebra"]]
    assert not peer.vouched_by_user

    # A second poll changes nothing; an older event never replaces a newer edge.
    assert (await mine.poll())["trust"] == 0


async def test_unconnected_offer_scores_zero_and_experience_from_attest():
    relay = InMemoryRelay(private=False)
    me, stranger = _zebra(), _zebra()
    mine = _exchange(me, relay)
    sha = "ab" * 32
    await mine.offers.add(
        OfferRecord(content_sha256=sha, name="X", publisher_pubkey=stranger["zebra"], event_id="e")
    )
    score = await mine.trust.score(stranger["zebra"], [(stranger["zebra"], WORKED)])
    assert score["score"] == 0.0 and not score["clears"]

    await mine.attest(REJECTED_ETHICS, sha)
    edge = await mine.trust.store.get_edge(me["zebra"], stranger["zebra"])
    assert edge.weight == pytest.approx(-0.2) and edge.reason == "experience"
    trusts = [e for e in relay.events if e.kind == TRUST_KIND]
    assert len(trusts) == 1 and verify_trust(trusts[0], [me["cert"]]).weight == -0.2
    peer = await mine.trust.store.get_peer(stranger["zebra"])
    assert peer.local_trust == pytest.approx(-0.2)


async def test_exchange_without_trust_fetches_no_trust():
    relay = InMemoryRelay(private=False)
    me = _zebra()
    exchange = CommonsExchange(publisher=_publisher(me, relay), offers=InMemoryOfferStore())
    counts = await exchange.poll()
    assert "trust" not in counts
    assert await exchange.fetch_trust() == 0


async def test_forged_trust_on_the_relay_is_refused():
    relay = InMemoryRelay(private=False)
    me, a, liar = _zebra(), _zebra(), _zebra()
    mine = _exchange(me, relay)
    await mine.trust.vouch(a["zebra"])
    # A device with no cert claims to be A and trusts the liar.
    wrong = sign_event(
        liar["device"],
        TRUST_KIND,
        trust_tags(liar["zebra"], a["zebra"]),
        trust_content(1.0, "vouched"),
    )
    relay.store(wrong)
    await mine.poll()
    assert await mine.trust.store.get_edge(a["zebra"], liar["zebra"]) is None
    assert (await mine.trust.trust_map()).get(liar["zebra"], 0.0) == 0.0


async def test_peer_record_defaults():
    store = InMemoryTrustStore()
    peer = await store.touch_peer(A, 10)
    assert peer == PeerRecord(pubkey=A, last_seen=10)
    assert (await store.touch_peer(A, 5)).last_seen == 10
