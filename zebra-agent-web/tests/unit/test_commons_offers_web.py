"""Offers and attestations, web side (#232, S5): wiring, the offer store, the /commons/ section.

Off unless a publisher exists (Commons on + ZEBRA_COMMONS_RELAYS + identity). Nothing here
contacts a relay: the page reads the database only, and the import tests use an in-memory one.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from zebra_agent.commons import keys
from zebra_agent.commons.attest import build_attest
from zebra_agent.commons.client import InMemoryCommonsClient, InMemoryRelay
from zebra_agent.commons.exchange import EXCHANGE_KEY, CommonsExchange
from zebra_agent.commons.identity import make_device_cert
from zebra_agent.commons.mirror import InMemoryCommonsMirror
from zebra_agent.commons.offer import build_offer, offer_content
from zebra_agent.commons.offers import (
    ADOPTED,
    JUDGING,
    REJECTED,
    SEEN,
    InMemoryOfferStore,
    InvalidOfferTransition,
    OfferRecord,
)
from zebra_agent.commons.publisher import CommonsPublisher
from zebra_agent.provenance import content_sha256
from zebra_agent_web.api import agent_engine, commons_exchange, commons_publish
from zebra_agent_web.api import commons_identity as ci
from zebra_agent_web.api.models import (
    CommonsDeviceModel,
    SystemStateModel,
    WorkflowOfferModel,
)
from zebra_agent_web.commons_mirror_store import DjangoCommonsMirror
from zebra_agent_web.commons_offer_store import DjangoOfferStore

RELAY = "ws://127.0.0.1:17996/commons"  # never contacted
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
SHA = content_sha256(YAML)


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


def _zebra() -> dict:
    zebra_secret, device_secret = keys.generate_secret_key(), keys.generate_secret_key()
    cert = make_device_cert(
        zebra_secret, keys.public_key(device_secret), label="Home", sphere="home", observed=False
    )
    return {"zebra": keys.public_key(zebra_secret), "device": device_secret, "cert": cert}


def _offer(z: dict):
    content = offer_content(
        name="Capital Facts",
        summary="Answers capital-city questions.",
        use_when="A capital question",
        stats={"runs": 6, "success_rate": 0.83, "avg_rating": 4.5, "gym_score": 0.9},
        actions=["llm_call"],
        golden_tasks=[{"goal": "Capital of Australia?", "expected": "Canberra", "criteria": ["c"]}],
        yaml=YAML,
    )
    return build_offer(
        content, device_secret=z["device"], zebra_pubkey=z["zebra"], chain=[z["cert"]]
    )


def _attest(z: dict, label: str, created_at: int | None = None):
    return build_attest(
        label,
        SHA,
        device_secret=z["device"],
        zebra_pubkey=z["zebra"],
        chain=[z["cert"]],
        created_at=created_at,
    )


async def _owner(user) -> None:
    await SystemStateModel.objects.aupdate_or_create(
        pk=1, defaults={"commons_owner_user_id": user.id, "setup_completed": True}
    )


# -- wiring ----------------------------------------------------------------------------------


async def test_no_exchange_without_a_publisher():
    assert await commons_exchange.build_commons_exchange(None) is None


@pytest.mark.django_db(transaction=True)
async def test_exchange_built_over_the_publisher(configure, clean, tmp_path):
    await ci.start_zebra(display_name="Z", label="Home box", sphere="home", observed=False)
    publisher = await commons_publish.build_commons_publisher(
        SimpleNamespace(library_path=tmp_path / "workflows")
    )
    exchange = await commons_exchange.build_commons_exchange(publisher)
    assert isinstance(exchange, CommonsExchange) and exchange.publisher is publisher
    assert isinstance(exchange.offers, DjangoOfferStore)
    await publisher.close()


async def test_exchange_tick_is_a_no_op_without_an_exchange_and_never_raises():
    await commons_exchange.exchange_tick(SimpleNamespace(extras={}))

    class Failing(CommonsExchange):
        def __init__(self):
            pass

        async def poll(self):
            raise RuntimeError("relay down")

    await commons_exchange.exchange_tick(SimpleNamespace(extras={EXCHANGE_KEY: Failing()}))


async def test_publish_tick_reads_offers_through_the_exchange(monkeypatch):
    calls = []

    async def tick(engine):
        calls.append(engine)

    monkeypatch.setattr(commons_exchange, "exchange_tick", tick)

    class Publisher(CommonsPublisher):
        def __init__(self):
            pass

        async def refresh_receipts(self):
            return 0

    engine = SimpleNamespace(extras={"__commons_publisher__": Publisher()})
    await commons_publish.publish_tick(engine)
    assert calls == [engine]
    await commons_publish.publish_tick(SimpleNamespace(extras={}))  # no publisher: nothing
    assert calls == [engine]


# -- the offer store -------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
async def test_django_offer_store_one_row_per_hash_and_transitions(clean):
    store = DjangoOfferStore(owner_user_id=7)
    record = OfferRecord(
        content_sha256=SHA, name="Capital Facts", publisher_pubkey="ab" * 32, event_id="e" * 64
    )
    assert await store.add(record) is True
    assert await store.add(record) is False
    row = await WorkflowOfferModel.objects.aget(content_sha256=SHA)
    assert (row.status, row.user_id) == (SEEN, 7)
    await store.set_status(SHA, JUDGING)
    await store.set_status(SHA, REJECTED, {"stage": "gym", "label": "rejected-gym"})
    assert (await store.get(SHA)).judgement["stage"] == "gym"
    await store.set_status(SHA, JUDGING)
    await store.set_status(SHA, ADOPTED)
    with pytest.raises(InvalidOfferTransition):
        await store.set_status(SHA, SEEN)
    assert (await store.get(SHA)).status == ADOPTED
    with pytest.raises(KeyError):
        await store.set_status("0" * 64, JUDGING)
    assert [r.content_sha256 for r in await store.list()] == [SHA]


# -- the page --------------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
async def test_page_shows_empty_states_while_publishing_is_off(
    authenticated_async_client, test_user, configure, clean
):
    configure(relays="")
    await _owner(test_user)
    response = await authenticated_async_client.get("/commons/")
    html = response.content.decode()
    assert response.status_code == 200
    assert 'data-publishing="off"' in html and 'data-testid="commons-offers-off"' in html
    assert 'data-testid="offers-seen-empty"' in html and 'data-testid="my-offers-empty"' in html
    assert "Import this" not in html


@pytest.mark.django_db(transaction=True)
async def test_page_lists_offers_seen_with_counts_and_import_for_the_owner(
    authenticated_async_client, async_client, test_user, configure, clean
):
    await _owner(test_user)
    a, b = _zebra(), _zebra()
    offer = _offer(a)
    mirror = DjangoCommonsMirror(test_user.id)
    for event in (a["cert"], offer, b["cert"], _attest(b, "worked"), _attest(b, "adopted")):
        await mirror.add(event)
    await DjangoOfferStore(test_user.id).add(
        OfferRecord(
            content_sha256=SHA,
            name="Capital Facts",
            summary="Answers capital-city questions.",
            stats={"runs": 6, "success_rate": 0.83, "avg_rating": 4.5, "gym_score": 0.9},
            publisher_pubkey=a["zebra"],
            event_id=offer.id,
            offered_at=offer.created_at,
        )
    )
    response = await authenticated_async_client.get("/commons/")
    html = response.content.decode()
    assert 'data-publishing="on"' in html
    assert f'data-offer="{SHA}"' in html and 'data-status="seen"' in html
    assert keys.npub_encode(a["zebra"]) in html
    assert "1 worked · 0 failed · 1 adopted · 0 rejected" in html
    assert "83%" in html
    assert f'action="/commons/offers/{SHA}/import/"' in html

    other = await get_user_model().objects.acreate(username="not-the-owner")
    await async_client.aforce_login(other)
    html = (await async_client.get("/commons/")).content.decode()
    assert f'data-offer="{SHA}"' in html and "Import this" not in html
    response = await async_client.post(f"/commons/offers/{SHA}/import/")
    assert response.status_code == 403


@pytest.mark.django_db(transaction=True)
async def test_page_shows_zebras_verdict_in_its_voice(
    authenticated_async_client, test_user, configure, clean
):
    await _owner(test_user)
    store = DjangoOfferStore(test_user.id)
    await store.add(
        OfferRecord(
            content_sha256=SHA, name="Capital Facts", publisher_pubkey="ab" * 32, event_id="e"
        )
    )
    await store.set_status(SHA, JUDGING)
    await store.set_status(
        SHA,
        REJECTED,
        {
            "label": "rejected-gym",
            "voice": "I turned it down: it failed its own golden tasks when I tried them.",
            "reason": "mean score 0.2 below 0.6",
            "process_id": "p-1",
        },
    )
    html = (await authenticated_async_client.get("/commons/")).content.decode()
    assert "I turned it down: it failed its own golden tasks" in html
    assert "mean score 0.2 below 0.6" in html and "recorded reasoning" in html
    assert 'href="/processes/p-1/trace/"' in html
    assert 'data-status="rejected"' in html and "Import this" in html  # may try again


@pytest.mark.django_db(transaction=True)
async def test_my_offers_show_attestations_from_other_zebras_only(
    authenticated_async_client, test_user, configure, clean
):
    await _owner(test_user)
    await ci.start_zebra(display_name="Me", label="Home box", sphere="home", observed=False)
    state = await SystemStateModel.objects.aget(pk=1)
    device = await ci.get_commons_keys().device_secret()
    chain = await ci._chain_events(state.zebra_pubkey)
    me = {"zebra": state.zebra_pubkey, "device": device, "cert": chain[0]}
    b = _zebra()
    mirror = DjangoCommonsMirror(test_user.id)
    for event in (
        _offer(me),
        b["cert"],
        _attest(b, "adopted"),
        _attest(b, "failed"),
        _attest(me, "worked"),  # my own: not "from other Zebras"
    ):
        await mirror.add(event)
    html = (await authenticated_async_client.get("/commons/")).content.decode()
    assert f'data-my-offer="{SHA}"' in html
    assert "0 worked · 1 failed · 1 adopted · 0 rejected" in html


# -- "Import this" ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
async def test_import_this_is_refused_while_publishing_is_off(
    authenticated_async_client, test_user, configure, clean, monkeypatch
):
    await _owner(test_user)

    async def _ready():
        return None

    monkeypatch.setattr(agent_engine, "ensure_initialized", _ready)
    from zebra_agent_web.api import engine as engine_module

    monkeypatch.setattr(engine_module, "get_engine", lambda: SimpleNamespace(extras={}))
    response = await authenticated_async_client.post(f"/commons/offers/{SHA}/import/")
    assert response.status_code == 302 and "publishing+is+off" in response["Location"].lower()


@pytest.mark.django_db(transaction=True)
async def test_start_offer_import_starts_commons_import_on_the_offer(
    test_user, configure, clean, monkeypatch
):
    a, me = _zebra(), _zebra()
    relay = InMemoryRelay(private=False)
    publisher_a = CommonsPublisher(
        canonical=InMemoryCommonsClient(relay),
        device_secret=a["device"],
        zebra_pubkey=a["zebra"],
        mirror=InMemoryCommonsMirror(),
        certs=[a["cert"]],
        receipt_wait=0,
    )
    await publisher_a.publish_event(_offer(a))
    exchange = CommonsExchange(
        publisher=CommonsPublisher(
            canonical=InMemoryCommonsClient(relay),
            device_secret=me["device"],
            zebra_pubkey=me["zebra"],
            mirror=InMemoryCommonsMirror(),
            certs=[me["cert"]],
            receipt_wait=0,
        ),
        offers=InMemoryOfferStore(),
    )
    await exchange.poll()
    started = {}

    async def _ready():
        return None

    async def create(engine, definition, *, entry, properties):
        started.update(definition=definition, entry=entry, properties=properties)
        return SimpleNamespace(id="proc-1")

    async def start(engine, process_id):
        started["started"] = process_id

    from zebra_agent_web.api import commons_import
    from zebra_agent_web.api import engine as engine_module

    monkeypatch.setattr(agent_engine, "ensure_initialized", _ready)
    monkeypatch.setattr(
        agent_engine, "get_library", lambda: SimpleNamespace(get_workflow=lambda n: n)
    )
    monkeypatch.setattr(
        engine_module, "get_engine", lambda: SimpleNamespace(extras={EXCHANGE_KEY: exchange})
    )
    monkeypatch.setattr("zebra_tasks.launch.create_library_process", create)
    monkeypatch.setattr(commons_import, "_start", start)

    process_id = await commons_exchange.start_offer_import(SHA, user_id=test_user.id)
    assert process_id == "proc-1"
    assert started["definition"] == "Commons Import" and started["entry"] == "direct_run"
    assert '"format":"zebra-commons-offer"' in started["properties"]["offer_event"]
    assert started["properties"]["__user_id__"] == test_user.id
    assert (await exchange.offers.get(SHA)).status == JUDGING
    with pytest.raises(ci.CommonsError, match="cannot be imported"):
        await commons_exchange.start_offer_import(SHA, user_id=test_user.id)
    with pytest.raises(ci.CommonsError, match="not seen"):
        await commons_exchange.start_offer_import("0" * 64, user_id=test_user.id)
