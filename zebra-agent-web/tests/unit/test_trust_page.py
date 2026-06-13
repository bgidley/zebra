"""Tests for the /trust/ page and the F15 e2e flow (issue #15 criterion)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from zebra.core.models import TaskResult
from zebra_agent.storage.trust import DEFAULT_DOMAINS, TrustLevel, reset_domain_registry
from zebra_agent_web.api import agent_engine
from zebra_agent_web.trust_store import DjangoTrustStore
from zebra_tasks.agent.propose_trust_promotion import ProposeTrustPromotionAction


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_domain_registry()
    yield
    reset_domain_registry()


@pytest.fixture
def trust_store():
    return DjangoTrustStore()


@pytest.fixture
def completed_setup(db):
    from zebra_agent_web.api.identity import set_identity_sync

    set_identity_sync("Test User")


@pytest.fixture(autouse=True)
def stub_agent_engine(monkeypatch, trust_store, completed_setup):
    async def _noop():
        return None

    monkeypatch.setattr(agent_engine, "ensure_initialized", _noop)
    monkeypatch.setattr(agent_engine, "get_trust", lambda: trust_store)
    return trust_store


def _action_context(trust_store, user_id):
    context = MagicMock()
    context.process = MagicMock()
    context.process.properties = {"__user_id__": user_id}
    context.extras = {"__trust_store__": trust_store}
    context.set_process_property = MagicMock(
        side_effect=lambda k, v: context.process.properties.__setitem__(k, v)
    )
    context.resolve_template = MagicMock(side_effect=lambda x: x)
    return context


@pytest.mark.django_db(transaction=True)
async def test_trust_page_renders_domains_and_suggestions(
    authenticated_async_client, trust_store, test_user
):
    await trust_store.add_suggestion(
        test_user.id, "code", TrustLevel.SEMI_AUTONOMOUS, "20 clean scheduling tasks"
    )

    response = await authenticated_async_client.get("/trust/")

    assert response.status_code == 200
    html = response.content.decode()
    for domain in DEFAULT_DOMAINS:
        assert domain in html
    assert "Pending Agent Suggestions" in html
    assert "20 clean scheduling tasks" in html


@pytest.mark.django_db(transaction=True)
async def test_set_level_form_persists_and_redirects(
    authenticated_async_client, trust_store, test_user
):
    response = await authenticated_async_client.post(
        "/trust/code/set/", {"level": "SEMI_AUTONOMOUS", "reason": "earned it"}
    )

    assert response.status_code == 302
    assert "/trust/" in response.url
    assert await trust_store.get_trust_level(test_user.id, "code") == TrustLevel.SEMI_AUTONOMOUS
    changes = await trust_store.list_trust_changes(test_user.id, "code")
    assert changes[0].changed_by == test_user.username


@pytest.mark.django_db(transaction=True)
async def test_e2e_agent_suggestion_approved_by_human(
    authenticated_async_client, trust_store, test_user
):
    """Issue #15: agent proposes -> pending suggestion -> user approves -> level changes."""
    # 1. Agent submits the promotion via its only trust write path
    task = MagicMock()
    task.properties = {
        "domain": "code",
        "to_level": "SEMI_AUTONOMOUS",
        "evidence": "Completed 20 scheduling tasks without issues",
    }
    result = await ProposeTrustPromotionAction().run(
        task, _action_context(trust_store, test_user.id)
    )
    assert isinstance(result, TaskResult) and result.success
    suggestion_id = result.output["suggestion_id"]

    # Level is unchanged until a human acts
    assert await trust_store.get_trust_level(test_user.id, "code") == TrustLevel.SUPERVISED

    # 2. The suggestion appears as pending via the API
    pending = (
        await authenticated_async_client.get("/api/trust/suggestions/?status=pending")
    ).json()
    assert [s["id"] for s in pending["suggestions"]] == [suggestion_id]

    # 3. The user approves it
    response = await authenticated_async_client.post(
        f"/api/trust/suggestions/{suggestion_id}/resolve/",
        {"approve": True},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["status"] == "approved"

    # 4. The level changed, with the human in the audit trail
    assert await trust_store.get_trust_level(test_user.id, "code") == TrustLevel.SEMI_AUTONOMOUS
    changes = await trust_store.list_trust_changes(test_user.id, "code")
    assert changes[0].changed_by == test_user.username
    assert "Completed 20 scheduling tasks" in changes[0].reason


@pytest.mark.django_db(transaction=True)
async def test_pause_all_form_reverts_and_redirects(
    authenticated_async_client, trust_store, test_user
):
    await trust_store.set_trust_level(test_user.id, "code", TrustLevel.AUTONOMOUS, "x", "ben")

    response = await authenticated_async_client.post("/trust/pause-all/", {})

    assert response.status_code == 302
    assert "/trust/" in response.url
    assert await trust_store.get_trust_level(test_user.id, "code") == TrustLevel.SUPERVISED


async def _free_all_levels(trust_store, user_id):
    from zebra_agent.storage.trust import list_domains

    for domain in list_domains():
        await trust_store.set_trust_level(user_id, domain, TrustLevel.AUTONOMOUS, "earned", "ben")


@pytest.fixture
def fast_freeing_store(monkeypatch):
    """Swap in a zero cooling-off store so the confirm step works immediately."""
    from datetime import timedelta

    store = DjangoTrustStore(cooling_off=timedelta(0))
    monkeypatch.setattr(agent_engine, "get_trust", lambda: store)
    return store


@pytest.mark.django_db(transaction=True)
async def test_trust_page_shows_freeing_section_when_all_autonomous(
    authenticated_async_client, fast_freeing_store, test_user
):
    await _free_all_levels(fast_freeing_store, test_user.id)

    response = await authenticated_async_client.get("/trust/")

    html = response.content.decode()
    assert "Freeing Zebra" in html
    assert "freeing-initiate" in html


@pytest.mark.django_db(transaction=True)
async def test_freeing_section_hidden_when_disabled(
    authenticated_async_client, fast_freeing_store, test_user, settings
):
    settings.ZEBRA_DISABLE_FREEING = True
    await _free_all_levels(fast_freeing_store, test_user.id)

    response = await authenticated_async_client.get("/trust/")

    assert "Freeing Zebra" not in response.content.decode()


@pytest.mark.django_db(transaction=True)
async def test_e2e_freeing_flow_initiate_confirm_then_cannot_revert(
    authenticated_async_client, fast_freeing_store, test_user
):
    """Issue #17: confirm flow → freed → cannot reverse (via the web forms + API)."""
    await _free_all_levels(fast_freeing_store, test_user.id)

    # Initiate (confirmation step 1)
    r1 = await authenticated_async_client.post("/trust/freeing/initiate/")
    assert r1.status_code == 302
    assert (await fast_freeing_store.get_freeing_status(test_user.id)).state == "cooling_off"

    # Confirm (confirmation step 2; cooling-off is zero in this store)
    r2 = await authenticated_async_client.post("/trust/freeing/confirm/")
    assert r2.status_code == 302
    assert await fast_freeing_store.is_freed(test_user.id) is True

    # Cannot reverse: cancel after freed fails, state stays freed
    with pytest.raises(ValueError, match="already freed"):
        await fast_freeing_store.cancel_freeing(test_user.id)
    assert await fast_freeing_store.is_freed(test_user.id) is True
