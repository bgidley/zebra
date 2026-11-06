"""Skill sync wiring (#246): off unless the Commons is on, ZEBRA_SYNC_RELAY is set and the
device has a Zebra identity. Nothing connects to a relay here (the transport connects lazily).
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest
from zebra_agent.commons import keys
from zebra_agent.commons.relay import RelayCommonsClient
from zebra_agent.commons.sync import SyncService
from zebra_agent_web.api import commons_identity as ci
from zebra_agent_web.api import commons_sync
from zebra_agent_web.api.models import CommonsDeviceModel, SystemStateModel

RELAY = "ws://127.0.0.1:17999/sync"  # never contacted: nothing is published in these tests


@pytest.fixture
def configure(settings, tmp_path):
    def use(*, enabled=True, relay=RELAY, receipt_pubkey=""):
        settings.ZEBRA_AGENT_SETTINGS = {
            **settings.ZEBRA_AGENT_SETTINGS,
            "COMMONS_ENABLED": enabled,
            "COMMONS_KEY_DIR": str(tmp_path / "keys"),
            "SYNC_RELAY": relay,
            "SYNC_RECEIPT_PUBKEY": receipt_pubkey,
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

    assert prod_settings.ZEBRA_AGENT_SETTINGS["SYNC_RELAY"] == ""
    assert prod_settings.ZEBRA_AGENT_SETTINGS["SYNC_RECEIPT_PUBKEY"] == ""


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("enabled,relay", [(False, RELAY), (True, ""), (False, "")])
async def test_no_service_unless_commons_and_relay(configure, library, enabled, relay):
    configure(enabled=enabled, relay=relay)
    assert await commons_sync.build_sync_service(library) is None


@pytest.mark.django_db(transaction=True)
async def test_no_service_without_an_identity(configure, library, clean_state):
    assert await commons_sync.build_sync_service(library) is None


@pytest.mark.django_db(transaction=True)
async def test_service_built_with_relay_client_when_configured(configure, library, clean_state):
    operator = keys.public_key(keys.generate_secret_key())
    configure(receipt_pubkey=operator.upper())
    await ci.start_zebra(display_name="Z", label="Home box", sphere="home", observed=False)

    sync = await commons_sync.build_sync_service(library)

    assert isinstance(sync, SyncService)
    assert isinstance(sync.client, RelayCommonsClient)
    assert sync.client.transport.url == RELAY
    assert sync.client.outbox.path == library.library_path / ".sync" / "outbox.jsonl"
    assert sync.receipt_pubkey == operator
    assert sync.sphere == "home" and sync.device_label == "Home box"
    assert sync.own_cert() is not None  # the cert came from the database
    await sync.client.close()


def test_direction_is_the_stricter_of_env_and_device(monkeypatch):
    monkeypatch.delenv("ZEBRA_SYNC_DIRECTION", raising=False)
    assert commons_sync._direction("both") == "both"
    assert commons_sync._direction("receive") == "receive"
    assert commons_sync._direction("bogus") == "both"
    monkeypatch.setenv("ZEBRA_SYNC_DIRECTION", "send")
    assert commons_sync._direction("receive") == "off"
    assert commons_sync._direction("both") == "send"


async def test_sync_tick_does_nothing_without_a_service(library):
    engine = SimpleNamespace(extras={})
    await commons_sync.sync_tick(engine, library)
    engine = SimpleNamespace(extras={"__commons_sync__": object()})
    await commons_sync.sync_tick(engine, library)  # not a SyncService: ignored


async def test_sync_tick_runs_each_step_and_survives_failures(monkeypatch, library):
    calls = []

    class Sync(SyncService):
        def __init__(self):
            self.zebra_pubkey = "z"

        async def flush(self):
            calls.append("flush")
            raise RuntimeError("relay down")

        async def refresh(self, events=None):
            calls.append("refresh")

        async def publish_identity(self):
            calls.append("identity")

        async def receive_pending(self, engine, lib):
            calls.append("receive")

        def merge_certs(self, events):
            calls.append("certs")

    async def chain(_pubkey):
        return []

    monkeypatch.setattr(commons_sync, "_chain_events", chain)
    await commons_sync.sync_tick(SimpleNamespace(extras={"__commons_sync__": Sync()}), library)
    assert calls == ["certs", "flush", "refresh", "identity", "receive"]


def test_nostr_sdk_not_loaded_by_the_web_app_when_off():
    # Importing the wiring and the sync logic must not load the alpha library.
    import zebra_agent.commons.sync  # noqa: F401
    import zebra_agent_web.api.commons_sync  # noqa: F401

    loaded_by_others = "zebra_agent.commons.nostr" in sys.modules
    if not loaded_by_others:
        assert "nostr_sdk" not in sys.modules
