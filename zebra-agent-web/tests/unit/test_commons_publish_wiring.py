"""Commons publishing wiring and the local mirror model (#231).

Off unless the Commons is on, ZEBRA_COMMONS_RELAYS is set and the device has a Zebra identity.
Nothing connects to a relay here (the transport connects lazily).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from zebra_agent.commons import keys
from zebra_agent.commons.events import COMMONS_TAG, sign_event
from zebra_agent.commons.kinds import OFFER_KIND
from zebra_agent.commons.publisher import CommonsPublisher
from zebra_agent.commons.relay import RelayCommonsClient
from zebra_agent_web.api import commons_identity as ci
from zebra_agent_web.api import commons_publish
from zebra_agent_web.api.models import (
    AppendOnlyError,
    CommonsDeviceModel,
    CommonsEventModel,
    SystemStateModel,
)
from zebra_agent_web.commons_mirror_store import DjangoCommonsMirror

CANONICAL = "ws://127.0.0.1:17998/commons"  # never contacted
MIRROR = "ws://127.0.0.1:17997/commons"


@pytest.fixture
def configure(settings, tmp_path):
    def use(*, enabled=True, relays=f"{CANONICAL}, {MIRROR}", receipt_pubkey=""):
        settings.ZEBRA_AGENT_SETTINGS = {
            **settings.ZEBRA_AGENT_SETTINGS,
            "COMMONS_ENABLED": enabled,
            "COMMONS_KEY_DIR": str(tmp_path / "keys"),
            "COMMONS_RELAYS": relays,
            "COMMONS_RECEIPT_PUBKEY": receipt_pubkey,
        }

    use()
    return use


@pytest.fixture
def library(tmp_path):
    return SimpleNamespace(library_path=tmp_path / "workflows")


@pytest.fixture
def clean_state(db):
    CommonsDeviceModel.objects.all().delete()
    SystemStateModel.objects.filter(pk=1).delete()


def test_settings_default_to_off():
    from zebra_agent_web import settings as prod_settings

    assert prod_settings.ZEBRA_AGENT_SETTINGS["COMMONS_RELAYS"] == ""
    assert prod_settings.ZEBRA_AGENT_SETTINGS["COMMONS_RECEIPT_PUBKEY"] == ""


def test_relay_list_is_canonical_first_without_duplicates(configure):
    configure(relays=f" {CANONICAL}\n{MIRROR},{CANONICAL} ")
    assert commons_publish.commons_relays() == [CANONICAL, MIRROR]
    configure(relays="")
    assert commons_publish.commons_relays() == []


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("enabled,relays", [(False, CANONICAL), (True, ""), (False, "")])
async def test_no_publisher_unless_commons_and_relays(configure, library, enabled, relays):
    configure(enabled=enabled, relays=relays)
    assert await commons_publish.build_commons_publisher(library) is None


@pytest.mark.django_db(transaction=True)
async def test_no_publisher_without_an_identity(configure, library, clean_state):
    assert await commons_publish.build_commons_publisher(library) is None


@pytest.mark.django_db(transaction=True)
async def test_publisher_built_with_public_clients_when_configured(configure, library, clean_state):
    operator = keys.public_key(keys.generate_secret_key())
    configure(receipt_pubkey=operator.upper())
    await ci.start_zebra(display_name="Z", label="Home box", sphere="home", observed=False)

    publisher = await commons_publish.build_commons_publisher(library)

    assert isinstance(publisher, CommonsPublisher)
    assert isinstance(publisher.canonical, RelayCommonsClient)
    assert publisher.canonical.transport.url == CANONICAL and not publisher.canonical.private
    assert [m.transport.url for m in publisher.mirrors] == [MIRROR]
    assert publisher.receipt_pubkey == operator
    assert isinstance(publisher.mirror, DjangoCommonsMirror)
    assert publisher.identity_events()  # this device's cert came from the database
    await publisher.close()


def _event(content: str = '{"name": "x"}'):
    secret = keys.generate_secret_key()
    return sign_event(secret, OFFER_KIND, [["d", "ab" * 32], COMMONS_TAG], content)


@pytest.mark.django_db(transaction=True)
async def test_django_mirror_stores_each_event_once_with_the_owner():
    mirror = DjangoCommonsMirror(owner_user_id=7)
    event = _event()
    assert await mirror.add(event, relay_seq=3) is True
    assert await mirror.add(event) is False
    stored = await mirror.get(event.id)
    assert stored.event == event and stored.relay_seq == 3
    row = await CommonsEventModel.objects.aget(event_id=event.id)
    assert (row.kind, row.pubkey, row.user_id, row.content) == (
        OFFER_KIND,
        event.pubkey,
        7,
        {"name": "x"},
    )
    assert [m.event.id for m in await mirror.events(kind=OFFER_KIND)] == [event.id]
    text = _event("not json")
    await mirror.add(text)
    assert (await CommonsEventModel.objects.aget(event_id=text.id)).content == {"text": "not json"}


@pytest.mark.django_db
def test_mirror_rows_are_append_only():
    event = _event()
    row = CommonsEventModel.objects.create(
        event_id=event.id,
        kind=event.kind,
        pubkey=event.pubkey,
        created_at=event.created_at,
        content={},
        sig=event.sig,
        event=event.to_dict(),
        user_id=1,
    )
    row.relay_seq = 5
    with pytest.raises(AppendOnlyError):
        row.save()
    with pytest.raises(AppendOnlyError):
        row.delete()
    with pytest.raises(AppendOnlyError):
        CommonsEventModel.objects.filter(pk=row.pk).update(relay_seq=5)
    with pytest.raises(AppendOnlyError):
        CommonsEventModel.objects.all().delete()
    assert CommonsEventModel.objects.get(pk=row.pk).relay_seq is None


async def test_publish_tick_does_nothing_without_a_publisher_and_never_raises():
    await commons_publish.publish_tick(SimpleNamespace(extras={}))
    await commons_publish.publish_tick(SimpleNamespace(extras={"__commons_publisher__": object()}))

    class Failing(CommonsPublisher):
        def __init__(self):
            pass

        async def refresh_receipts(self):
            raise RuntimeError("relay down")

    failing = SimpleNamespace(extras={"__commons_publisher__": Failing()})
    await commons_publish.publish_tick(failing)
