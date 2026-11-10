"""Public genealogy pages (#247): public events in the mirror only, nothing private, off by default.

The two-Zebra test runs A and B over an in-memory relay (nothing real is contacted), then
renders A's ``/commons/genealogy/`` from A's mirror. A's library holds private ancestors and a
lineage journal, the mirror holds a ``SKILL`` event and a forged offer naming a private parent:
none of their hashes may appear in either page.
"""

from __future__ import annotations

import asyncio
from urllib.parse import parse_qs

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from tests.unit.test_workflow_genealogy import _prod_middleware
from zebra_agent.commons import keys
from zebra_agent.commons.client import InMemoryCommonsClient, InMemoryRelay
from zebra_agent.commons.events import COMMONS_TAG, PROTOCOL_VERSION_TAG, sign_event
from zebra_agent.commons.exchange import CommonsExchange
from zebra_agent.commons.identity import make_device_cert
from zebra_agent.commons.kinds import SKILL_KIND
from zebra_agent.commons.mirror import InMemoryCommonsMirror
from zebra_agent.commons.offer import build_offer, offer_content
from zebra_agent.commons.offers import InMemoryOfferStore
from zebra_agent.commons.publisher import CommonsPublisher
from zebra_agent.commons.trust import build_trust
from zebra_agent.genealogy import LineageJournal
from zebra_agent.library import WorkflowLibrary
from zebra_agent_web.api import agent_engine
from zebra_agent_web.api.models import CommonsEventModel, PeerModel, SystemStateModel

pytestmark = [pytest.mark.django_db(transaction=True)]

RELAY = "ws://127.0.0.1:17996/commons"  # never contacted


def _workflow(prompt: str) -> str:
    return f"""name: "Capital Facts"
description: "Answer questions about capital cities"
first_task: answer
tasks:
  answer:
    name: "Answer"
    action: llm_call
    properties:
      prompt: "{prompt}"
routings: []
"""


GOLDEN = [{"goal": "Capital of Australia?", "expected": "Canberra", "criteria": ["Canberra"]}]


def _content(yaml_text: str, name: str = "Capital Facts") -> dict:
    return offer_content(
        name=name,
        summary="Answers capital-city questions.",
        use_when="",
        stats={"runs": 6, "success_rate": 1.0, "avg_rating": 4.5, "gym_score": 0.9},
        actions=["llm_call"],
        golden_tasks=GOLDEN,
        yaml=yaml_text,
    )


def _zebra() -> dict:
    zebra_secret, device_secret = keys.generate_secret_key(), keys.generate_secret_key()
    cert = make_device_cert(
        zebra_secret, keys.public_key(device_secret), label="Home", sphere="home", observed=False
    )
    return {"zebra": keys.public_key(zebra_secret), "device": device_secret, "cert": cert}


def _exchange(z: dict, relay: InMemoryRelay) -> CommonsExchange:
    publisher = CommonsPublisher(
        canonical=InMemoryCommonsClient(relay),
        device_secret=z["device"],
        zebra_pubkey=z["zebra"],
        mirror=InMemoryCommonsMirror(),
        certs=[z["cert"]],
        receipt_wait=0,
    )
    return CommonsExchange(publisher=publisher, offers=InMemoryOfferStore())


def _store(event) -> None:
    content = event.json_content()
    CommonsEventModel.objects.create(
        event_id=event.id,
        kind=event.kind,
        pubkey=event.pubkey,
        created_at=event.created_at,
        content=content if content is not None else {"text": event.content},
        sig=event.sig,
        event=event.to_dict(),
    )


@pytest.fixture(autouse=True)
def completed_setup(db):
    from zebra_agent_web.api.identity import set_identity_sync

    set_identity_sync("Test User")
    PeerModel.objects.all().delete()
    SystemStateModel.objects.filter(pk=1).update(zebra_pubkey="")


@pytest.fixture
def configure(settings, tmp_path):
    def use(*, enabled=True, relays=""):
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
def client(db):
    c = Client()
    c.force_login(get_user_model().objects.create_user(username="genealogy-owner"))
    return c


@pytest.fixture
def private_library(tmp_path, monkeypatch):
    """A's library: two private versions before the offered one, all journaled."""
    library = WorkflowLibrary(tmp_path / "library-a", owner_user_id=1)
    library.add_workflow(_workflow("Draft: {{goal}}"))
    library.save(_workflow("Draft two: {{goal}}"), writer="optimizer", reason="private")
    library.save(_workflow("Answer: {{goal}}"), writer="optimizer", reason="private reason")

    async def _ready():
        return None

    # If the view ever read the library, it would find these.
    monkeypatch.setattr(agent_engine, "ensure_initialized", _ready)
    monkeypatch.setattr(agent_engine, "get_library", lambda: library)
    return library


def _two_zebras(library_a: WorkflowLibrary) -> dict:
    """A offers; B sees it, adopts it, reports a run, derives and offers a new version;
    A polls. Returns A's mirrored events and the hashes involved."""

    async def run() -> dict:
        relay = InMemoryRelay(private=False)
        a_keys, b_keys = _zebra(), _zebra()
        a, b = _exchange(a_keys, relay), _exchange(b_keys, relay)
        block_a = library_a.commons_block("Capital Facts")
        offered_a = await a.publisher.publish_offer(
            _content(_workflow("Answer: {{goal}}")), block_a
        )
        sha = offered_a["content_sha256"]
        await b.poll()
        await b.offers.set_status(sha, "judging")
        await b.record_import(sha, status="adopted", label="adopted", reason="owner-approved")
        await b.attest("worked", sha)
        derived = _workflow("Answer briefly and cite: {{goal}}")
        offered_b = await b.publisher.publish_offer(_content(derived), {"parent_sha256": sha})
        # A vouches for B (published), so the Zebra lineage has a link
        trust = build_trust(
            b_keys["zebra"],
            0.8,
            "vouched",
            device_secret=a_keys["device"],
            zebra_pubkey=a_keys["zebra"],
            chain=[a_keys["cert"]],
        )
        await a.publisher.publish_event(trust)
        await a.poll()
        events = [m.event for m in await a.mirror.events()]
        return {
            "events": events,
            "a": a_keys,
            "b": b_keys,
            "sha_a": sha,
            "sha_b": offered_b["content_sha256"],
            "parent_b": offered_b["parent"],
        }

    return asyncio.run(run())


def _private_hashes(library: WorkflowLibrary, public: set[str]) -> set[str]:
    block = library.commons_block("Capital Facts")
    hashes = {block.get("parent_sha256"), *(block.get("ancestors") or [])}
    hashes |= {
        r["content_sha256"]
        for r in LineageJournal(library.library_path).read()
        if r.get("content_sha256")
    }
    return {h for h in hashes if h} - public


def test_commons_off_shows_an_empty_state_and_offers_404(configure, client):
    configure(enabled=False)
    response = client.get("/commons/genealogy/")
    assert response.status_code == 200
    assert 'data-testid="genealogy-off"' in response.content.decode()
    assert client.get(f"/commons/genealogy/{'ab' * 32}/").status_code == 404


def test_empty_mirror_shows_empty_states(configure, client):
    html = client.get("/commons/genealogy/").content.decode()
    assert 'data-testid="lineage-empty"' in html and 'data-testid="trust-empty"' in html
    assert 'data-testid="genealogy-publishing-off"' in html
    assert "price" not in html.lower()


def test_two_zebras_a_sees_bs_derived_offer_and_nothing_private(configure, client, private_library):
    """O1 + O2 + O3: A's public genealogy after B adopted, ran, derived and offered."""
    world = _two_zebras(private_library)
    sha_a, sha_b, a, b = world["sha_a"], world["sha_b"], world["a"], world["b"]
    assert world["parent_b"] == sha_a  # B named A's public offer as parent

    for event in world["events"]:
        _store(event)
    # Defence in depth: a private SKILL event and an offer naming a private parent
    private = _private_hashes(private_library, {sha_a})
    assert len(private) == 2
    hidden_parent = sorted(private)[0]
    skill = sign_event(a["device"], SKILL_KIND, [COMMONS_TAG, PROTOCOL_VERSION_TAG], "secret")
    _store(skill)
    forged = build_offer(
        _content(_workflow("Other: {{goal}}"), name="River Facts"),
        device_secret=a["device"],
        zebra_pubkey=a["zebra"],
        chain=[a["cert"]],
        parent=hidden_parent,
    )
    _store(forged)
    SystemStateModel.objects.update_or_create(pk=1, defaults={"zebra_pubkey": a["zebra"]})
    PeerModel.objects.create(
        pubkey=b["zebra"],
        display_name="Bea's Zebra",
        vouched_by_user=True,
        owner_weight=0.8,
        local_trust=0.8,
        best_path={"value": 0.8, "hops": [[a["zebra"], b["zebra"], 0.8]]},
    )

    response = client.get("/commons/genealogy/")
    assert response.status_code == 200
    html = response.content.decode()
    # Workflow lineage: A's offer → B's derived offer, B adopted and ran A's
    assert f'data-offer="{sha_a}"' in html and f'data-offer="{sha_b}"' in html
    card_b = html.split(f'data-offer="{sha_b}"', 1)[1].split("</article>", 1)[0]
    assert f'href="/commons/genealogy/{sha_a}/"' in card_b and "Bea&#x27;s Zebra" in card_b
    card_a = html.split(f'data-offer="{sha_a}"', 1)[1].split("</article>", 1)[0]
    assert 'data-testid="offer-adopted"><span class="font-mono tabular-nums">1</span>' in card_a
    assert 'data-label="adopted" data-reason="owner-approved"' in card_a
    assert 'data-label="worked" data-reason="run-succeeded"' in card_a
    assert keys.npub_encode(a["zebra"]) in card_a
    # Zebra lineage: A vouches for B, and my path to B
    assert f'data-from="{a["zebra"]}" data-to="{b["zebra"]}" data-weight="0.80"' in html
    assert "Bea&#x27;s Zebra directly: 0.8 = 0.80" in html
    assert 'class="genealogy-graph"' in html and "trust-arrow" in html
    # Privacy: no private ancestor, journal record or SKILL event, anywhere
    for secret in (*private, skill.id):
        assert secret not in html, secret
    assert "secret" not in html

    # Per-offer page: B's family is A → B; private hashes and the SKILL event 404
    offer = client.get(f"/commons/genealogy/{sha_b}/")
    assert offer.status_code == 200
    page = offer.content.decode()
    assert f'data-offer="{sha_a}"' in page and 'data-testid="offer-parent"' in page
    for secret in (*private, skill.id):
        assert secret not in page
        assert client.get(f"/commons/genealogy/{secret}/").status_code == 404
    forged_sha = forged.tag_values("d")[0]
    forged_page = client.get(f"/commons/genealogy/{forged_sha}/").content.decode()
    assert hidden_parent not in forged_page and 'data-testid="offer-parent"' not in forged_page


def test_my_offers_are_marked_mine(configure, client):
    a = _zebra()
    offer = build_offer(
        _content(_workflow("Answer: {{goal}}")),
        device_secret=a["device"],
        zebra_pubkey=a["zebra"],
        chain=[a["cert"]],
    )
    _store(offer)
    SystemStateModel.objects.update_or_create(pk=1, defaults={"zebra_pubkey": a["zebra"]})
    html = client.get("/commons/genealogy/").content.decode()
    assert ">mine</span>" in html and "me</span>" in html


@pytest.mark.parametrize("path", ["/commons/genealogy/", f"/commons/genealogy/{'ab' * 32}/"])
def test_pages_are_behind_login(configure, settings, path):
    settings.MIDDLEWARE = _prod_middleware()
    anonymous = Client().get(path)
    assert anonymous.status_code == 302
    login, _, query = anonymous.url.partition("?")
    assert login == settings.LOGIN_URL
    assert parse_qs(query)["next"] == [path]


def test_commons_page_links_to_the_public_genealogy(configure, client):
    html = client.get("/commons/").content.decode()
    assert 'href="/commons/genealogy/"' in html
