"""Web of trust, web side (#233, S6): store, wiring, owner actions, the /commons/ peers section.

Off unless a publisher exists; with publishing off the owner's vouches stay local. Nothing here
contacts a real relay: the multi-Zebra test uses an in-memory one.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from zebra_agent.commons import keys
from zebra_agent.commons.client import InMemoryCommonsClient, InMemoryRelay
from zebra_agent.commons.exchange import EXCHANGE_KEY, CommonsExchange
from zebra_agent.commons.identity import fingerprint, make_device_cert
from zebra_agent.commons.kinds import TRUST_KIND
from zebra_agent.commons.mirror import InMemoryCommonsMirror
from zebra_agent.commons.offer import build_offer, offer_content
from zebra_agent.commons.peers import InMemoryTrustStore, PeerRecord, TrustEdge
from zebra_agent.commons.publisher import CommonsPublisher
from zebra_agent.commons.trust import verify_trust
from zebra_agent.commons.web_of_trust import WebOfTrust
from zebra_agent_web.api import agent_engine, commons_exchange, commons_publish
from zebra_agent_web.api import commons_identity as ci
from zebra_agent_web.api import engine as engine_module
from zebra_agent_web.api.models import (
    CommonsDeviceModel,
    PeerModel,
    SystemStateModel,
    TrustEdgeModel,
    WorkflowOfferModel,
)
from zebra_agent_web.commons_mirror_store import DjangoCommonsMirror
from zebra_agent_web.commons_offer_store import DjangoOfferStore
from zebra_agent_web.commons_peer_store import DjangoPeerTrustStore

RELAY = "ws://127.0.0.1:17995/commons"  # never contacted
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


@pytest.fixture(autouse=True)
def completed_setup(db):
    from zebra_agent_web.api.identity import set_identity_sync

    set_identity_sync("Test User")


@pytest.fixture
def configure(settings, tmp_path):
    def use(*, enabled=True, relays=RELAY):
        settings.ZEBRA_AGENT_SETTINGS = {
            **settings.ZEBRA_AGENT_SETTINGS,
            "COMMONS_ENABLED": enabled,
            "COMMONS_KEY_DIR": str(tmp_path / "keys"),
            "COMMONS_RELAYS": relays,
            "COMMONS_RECEIPT_PUBKEY": "",
        }

    use()
    return use


@pytest.fixture
def clean(db):
    CommonsDeviceModel.objects.all().delete()
    SystemStateModel.objects.filter(pk=1).update(zebra_pubkey="", device_pubkey="")
    WorkflowOfferModel.objects.all().delete()
    PeerModel.objects.all().delete()
    TrustEdgeModel.objects.all().delete()


@pytest.fixture
def engine_extras(monkeypatch):
    """The engine's extras, empty by default (publishing off)."""
    extras: dict = {}

    async def _ready():
        return None

    monkeypatch.setattr(agent_engine, "ensure_initialized", _ready)
    monkeypatch.setattr(engine_module, "get_engine", lambda: SimpleNamespace(extras=extras))
    return extras


def _zebra() -> dict:
    zebra_secret, device_secret = keys.generate_secret_key(), keys.generate_secret_key()
    cert = make_device_cert(
        zebra_secret, keys.public_key(device_secret), label="Home", sphere="home", observed=False
    )
    return {"zebra": keys.public_key(zebra_secret), "device": device_secret, "cert": cert}


def _publisher(z: dict, relay: InMemoryRelay) -> CommonsPublisher:
    return CommonsPublisher(
        canonical=InMemoryCommonsClient(relay),
        device_secret=z["device"],
        zebra_pubkey=z["zebra"],
        mirror=InMemoryCommonsMirror(),
        certs=[z["cert"]],
        receipt_wait=0,
    )


async def _owner(user) -> None:
    await SystemStateModel.objects.aupdate_or_create(
        pk=1, defaults={"commons_owner_user_id": user.id, "setup_completed": True}
    )


async def _me() -> dict:
    await ci.start_zebra(display_name="Me", label="Home box", sphere="home", observed=False)
    state = await SystemStateModel.objects.aget(pk=1)
    device = await ci.get_commons_keys().device_secret()
    chain = await ci._chain_events(state.zebra_pubkey)
    return {"zebra": state.zebra_pubkey, "device": device, "cert": chain[0]}


# -- store and wiring ------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
async def test_django_store_round_trip_and_latest_wins(clean):
    store = DjangoPeerTrustStore(owner_user_id=7)
    a, b = "a" * 64, "b" * 64
    await store.save_peer(PeerRecord(pubkey=a, display_name="A", vouched_by_user=True))
    peer = await store.get_peer(a)
    assert peer.vouched_by_user and peer.display_name == "A"
    assert (await PeerModel.objects.aget(pubkey=a)).user_id == 7
    assert await store.put_if_newer(TrustEdge(a, b, 0.6, "vouched", "e2" * 32, created_at=20))
    assert not await store.put_if_newer(TrustEdge(a, b, 0.1, "vouched", "e1" * 32, created_at=10))
    edge = await store.get_edge(a, b)
    assert edge.weight == 0.6 and edge.created_at == 20
    assert await TrustEdgeModel.objects.acount() == 1
    assert [e.to_pubkey for e in await store.list_edges()] == [b]


@pytest.mark.django_db(transaction=True)
async def test_django_store_writers_touch_only_their_columns(clean):
    """A recompute or a touch holding an older peer never puts back owner fields (#233 review)."""
    store = DjangoPeerTrustStore(owner_user_id=7)
    a, b = "a" * 64, "b" * 64
    await store.set_owner_fields(a, vouched_by_user=True, owner_weight=0.8, display_name="A")
    await store.set_computed(a, 0.8, {"value": 0.8})
    await store.set_owner_fields(a, vouched_by_user=False, owner_weight=-0.8)  # distrust
    await store.set_computed(a, 0.5, {"value": 0.5})  # a stale recompute's write
    peer = await store.touch_peer(a, 40)
    assert not peer.vouched_by_user and peer.owner_weight == -0.8 and peer.display_name == "A"
    assert peer.local_trust == 0.5 and peer.last_seen == 40
    assert (await store.touch_peer(a, 10)).last_seen == 40
    assert (await store.touch_peer(b)).last_seen == 0
    assert (await PeerModel.objects.aget(pubkey=b)).user_id == 7

    first = TrustEdge(a, b, 0.8, "vouched", created_at=10, pending=True)
    await store.save_edge(first)
    assert (await store.get_edge(a, b)).pending
    await store.save_edge(TrustEdge(a, b, 0.0, "withdrawn", created_at=11, pending=True))
    kwargs = {"event_id": "e" * 64, "created_at": 12, "relay_seq": 3}
    assert not await store.mark_published(first, published_weight=0.8, **kwargs)
    newer = await store.get_edge(a, b)
    assert newer.pending and newer.published_weight is None
    assert await store.mark_published(newer, published_weight=0.0, **kwargs)
    edge = await store.get_edge(a, b)
    assert not edge.pending and edge.published_weight == 0.0 and edge.relay_seq == 3


@pytest.mark.django_db(transaction=True)
async def test_exchange_carries_the_web_of_trust(configure, clean, tmp_path):
    await ci.start_zebra(display_name="Z", label="Home box", sphere="home", observed=False)
    publisher = await commons_publish.build_commons_publisher(
        SimpleNamespace(library_path=tmp_path / "workflows")
    )
    exchange = await commons_exchange.build_commons_exchange(publisher)
    assert isinstance(exchange.trust, WebOfTrust)
    assert exchange.trust.publisher is publisher
    assert isinstance(exchange.trust.store, DjangoPeerTrustStore)
    await publisher.close()


@pytest.mark.django_db(transaction=True)
async def test_no_publisher_when_relays_are_unset(configure, clean, tmp_path):
    configure(relays="")
    await ci.start_zebra(display_name="Z", label="Home box", sphere="home", observed=False)
    publisher = await commons_publish.build_commons_publisher(
        SimpleNamespace(library_path=tmp_path / "workflows")
    )
    assert publisher is None
    assert await commons_exchange.build_commons_exchange(publisher) is None


# -- the page and the owner's actions --------------------------------------------------------


@pytest.mark.django_db(transaction=True)
async def test_peers_section_empty_while_publishing_is_off(
    authenticated_async_client, test_user, configure, clean
):
    configure(relays="")
    await _owner(test_user)
    await _me()
    html = (await authenticated_async_client.get("/commons/")).content.decode()
    assert 'data-testid="commons-peers"' in html and 'data-testid="commons-peers-off"' in html
    assert 'data-testid="peers-empty"' in html and 'data-testid="vouch-form"' in html


@pytest.mark.django_db(transaction=True)
async def test_owner_vouch_with_publishing_off_is_local(
    authenticated_async_client, test_user, configure, clean, engine_extras
):
    configure(relays="")
    await _owner(test_user)
    me = await _me()
    a = _zebra()
    response = await authenticated_async_client.post(
        "/commons/peers/",
        {"action": "vouch", "zebra": keys.npub_encode(a["zebra"]), "display_name": "Alice"},
    )
    assert response.status_code == 302 and "kept+here" in response["Location"]
    peer = await PeerModel.objects.aget(pubkey=a["zebra"])
    assert peer.vouched_by_user and peer.display_name == "Alice"
    assert peer.local_trust == pytest.approx(0.8)
    edge = await TrustEdgeModel.objects.aget(from_pubkey=me["zebra"], to_pubkey=a["zebra"])
    assert edge.weight == 0.8 and edge.event_id == "" and edge.published_weight is None
    html = (await authenticated_async_client.get("/commons/")).content.decode()
    assert f'data-peer="{a["zebra"]}"' in html and 'data-testid="peer-vouched"' in html
    assert "Alice directly: 0.8 = 0.80" in html
    assert "You told me you know this Zebra" in html

    await authenticated_async_client.post(
        "/commons/peers/", {"action": "distrust", "zebra": a["zebra"]}
    )
    peer = await PeerModel.objects.aget(pubkey=a["zebra"])
    assert not peer.vouched_by_user and peer.local_trust == pytest.approx(-0.8)
    await authenticated_async_client.post(
        "/commons/peers/", {"action": "withdraw", "zebra": a["zebra"]}
    )
    assert (await PeerModel.objects.aget(pubkey=a["zebra"])).local_trust == 0.0


@pytest.mark.django_db(transaction=True)
async def test_bad_key_and_self_are_refused(
    authenticated_async_client, test_user, configure, clean, engine_extras
):
    await _owner(test_user)
    me = await _me()
    response = await authenticated_async_client.post(
        "/commons/peers/", {"action": "vouch", "zebra": "npub1nope"}
    )
    assert "error=" in response["Location"]
    response = await authenticated_async_client.post(
        "/commons/peers/", {"action": "vouch", "zebra": me["zebra"]}
    )
    assert "itself" in response["Location"]
    assert await PeerModel.objects.acount() == 0


@pytest.mark.django_db(transaction=True)
async def test_only_the_owner_can_vouch(async_client, test_user, configure, clean):
    await _owner(test_user)
    await _me()
    other = await get_user_model().objects.acreate(username="not-the-owner")
    await async_client.aforce_login(other)
    html = (await async_client.get("/commons/")).content.decode()
    assert 'data-testid="vouch-form"' not in html
    response = await async_client.post(
        "/commons/peers/", {"action": "vouch", "zebra": _zebra()["zebra"]}
    )
    assert response.status_code == 403
    assert await PeerModel.objects.acount() == 0


@pytest.mark.django_db(transaction=True)
async def test_commons_off_is_404(authenticated_async_client, test_user, configure, clean):
    configure(enabled=False)
    await _owner(test_user)
    response = await authenticated_async_client.post(
        "/commons/peers/", {"action": "vouch", "zebra": _zebra()["zebra"]}
    )
    assert response.status_code == 404


# -- several Zebras --------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
async def test_owner_vouches_a_a_trusts_b_and_unconnected_offer_scores_zero(
    authenticated_async_client, test_user, configure, clean, engine_extras
):
    """#233 E2E: the owner vouches A, A's owner vouches B; /commons/ shows B via A. An offer
    from a Zebra no one vouches for scores 0 and is flagged."""
    await _owner(test_user)
    me = await _me()
    a, b, stranger = _zebra(), _zebra(), _zebra()
    relay = InMemoryRelay(private=False)

    zebra_a = WebOfTrust(InMemoryTrustStore(), a["zebra"], publisher=_publisher(a, relay))
    await zebra_a.vouch(b["zebra"])

    my_publisher = _publisher(me, relay)
    my_publisher.mirror = DjangoCommonsMirror(test_user.id)
    exchange = CommonsExchange(
        publisher=my_publisher,
        offers=DjangoOfferStore(test_user.id),
        trust=WebOfTrust(DjangoPeerTrustStore(test_user.id), me["zebra"], publisher=my_publisher),
    )
    engine_extras[EXCHANGE_KEY] = exchange

    response = await authenticated_async_client.post(
        "/commons/peers/",
        {"action": "vouch", "zebra": keys.npub_encode(a["zebra"]), "display_name": "A"},
    )
    assert "published" in response["Location"]
    [mine] = [
        e for e in relay.events if e.kind == TRUST_KIND and e.tag_values("zebra") == [me["zebra"]]
    ]
    assert verify_trust(mine, [me["cert"]]).to_pubkey == a["zebra"]
    assert json.loads(mine.content) == {"reason": "vouched", "weight": 0.8}

    offer = build_offer(
        offer_content(
            name="Stranger Facts",
            summary="From a Zebra no one knows.",
            use_when="Never",
            stats={"runs": 6, "success_rate": 1.0, "avg_rating": 5, "gym_score": 1.0},
            actions=["llm_call"],
            golden_tasks=[{"goal": "Capital?", "expected": "Canberra", "criteria": ["c"]}],
            yaml=YAML,
        ),
        device_secret=stranger["device"],
        zebra_pubkey=stranger["zebra"],
        chain=[stranger["cert"]],
    )
    relay.store(stranger["cert"])
    relay.store(offer)
    relay.store(a["cert"])

    counts = await exchange.poll()
    assert counts["ok"] == 1 and counts["trust"] >= 1

    peer_b = await PeerModel.objects.aget(pubkey=b["zebra"])
    assert peer_b.local_trust == pytest.approx(0.8 * 0.8 * 0.9)
    html = (await authenticated_async_client.get("/commons/")).content.decode()
    assert f'data-peer="{b["zebra"]}"' in html
    assert f"{fingerprint(b['zebra'])} via A: 0.8 × 0.8 × 0.9 = 0.58" in html
    assert "I trust it through Zebras you know" in html

    assert 'data-score="0.000"' in html and 'data-clears="no"' in html
    assert 'data-testid="offer-score-warning"' in html
    assert "no Zebra you know vouches for its publisher" in html
