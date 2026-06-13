"""Tests for the trust management API endpoints (F15 / REQ-TRUST-004)."""

from __future__ import annotations

import pytest
from zebra_agent.storage.trust import TrustLevel, reset_domain_registry
from zebra_agent_web.api import agent_engine
from zebra_agent_web.trust_store import DjangoTrustStore


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_domain_registry()
    yield
    reset_domain_registry()


@pytest.fixture
def trust_store():
    return DjangoTrustStore()


@pytest.fixture(autouse=True)
def stub_agent_engine(monkeypatch, trust_store):
    """Route the views' trust store lookup straight to a Django store."""

    async def _noop():
        return None

    monkeypatch.setattr(agent_engine, "ensure_initialized", _noop)
    monkeypatch.setattr(agent_engine, "get_trust", lambda: trust_store)
    return trust_store


@pytest.mark.django_db(transaction=True)
def test_endpoints_require_auth(client):
    assert client.get("/api/trust/").status_code in (302, 401, 403)
    assert client.post("/api/trust/code/", {}, content_type="application/json").status_code in (
        302,
        401,
        403,
    )


@pytest.mark.django_db(transaction=True)
def test_get_trust_levels(authenticated_client):
    response = authenticated_client.get("/api/trust/")

    assert response.status_code == 200
    levels = response.json()["levels"]
    assert levels["code"] == "SUPERVISED"
    assert len(levels) == 8


@pytest.mark.django_db(transaction=True)
def test_set_level_writes_audit_with_changed_by(authenticated_client, test_user, trust_store):
    response = authenticated_client.post(
        "/api/trust/code/",
        {"level": "SEMI_AUTONOMOUS", "reason": "20 clean runs"},
        content_type="application/json",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["new_level"] == "SEMI_AUTONOMOUS"
    assert body["changed_by"] == test_user.username

    changes = authenticated_client.get("/api/trust/changes/?domain=code").json()["changes"]
    assert len(changes) == 1
    assert changes[0]["changed_by"] == test_user.username
    assert changes[0]["reason"] == "20 clean runs"


@pytest.mark.django_db(transaction=True)
def test_set_invalid_level_returns_400(authenticated_client):
    response = authenticated_client.post(
        "/api/trust/code/", {"level": "OMNIPOTENT"}, content_type="application/json"
    )
    assert response.status_code == 400

    response = authenticated_client.post(
        "/api/trust/time-travel/", {"level": "AUTONOMOUS"}, content_type="application/json"
    )
    assert response.status_code == 400

    assert authenticated_client.get("/api/trust/changes/").json()["changes"] == []


@pytest.mark.django_db(transaction=True)
def test_suggestion_list_and_resolve_flow(authenticated_client, test_user, trust_store):
    import asyncio

    suggestion = asyncio.run(
        trust_store.add_suggestion(
            test_user.id, "code", TrustLevel.SEMI_AUTONOMOUS, "20 clean runs"
        )
    )

    pending = authenticated_client.get("/api/trust/suggestions/?status=pending").json()
    assert [s["id"] for s in pending["suggestions"]] == [suggestion.id]

    response = authenticated_client.post(
        f"/api/trust/suggestions/{suggestion.id}/resolve/",
        {"approve": True},
        content_type="application/json",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["resolved_by"] == test_user.username

    levels = authenticated_client.get("/api/trust/").json()["levels"]
    assert levels["code"] == "SEMI_AUTONOMOUS"


@pytest.mark.django_db(transaction=True)
def test_resolve_unknown_suggestion_returns_400(authenticated_client):
    response = authenticated_client.post(
        "/api/trust/suggestions/nope/resolve/",
        {"approve": True},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db(transaction=True)
def test_pause_all_requires_auth(client):
    assert client.post(
        "/api/trust/pause-all/", {}, content_type="application/json"
    ).status_code in (
        302,
        401,
        403,
    )


@pytest.mark.django_db(transaction=True)
def test_pause_all_reverts_and_audits(authenticated_client, test_user, trust_store):
    import asyncio

    asyncio.run(
        trust_store.set_trust_level(test_user.id, "code", TrustLevel.AUTONOMOUS, "x", "ben")
    )

    response = authenticated_client.post(
        "/api/trust/pause-all/", {"reason": "stop now"}, content_type="application/json"
    )

    assert response.status_code == 200
    assert response.json()["reverted"] == ["code"]
    levels = authenticated_client.get("/api/trust/").json()["levels"]
    assert levels["code"] == "SUPERVISED"
    latest = authenticated_client.get("/api/trust/changes/?domain=code").json()["changes"][0]
    assert latest["changed_by"] == test_user.username
    assert "Emergency override" in latest["reason"]


async def _free_all(trust_store, user_id):
    from zebra_agent.storage.trust import list_domains

    for domain in list_domains():
        await trust_store.set_trust_level(user_id, domain, TrustLevel.AUTONOMOUS, "earned", "ben")


@pytest.fixture
def fast_freeing(monkeypatch):
    """Use a zero cooling-off DjangoTrustStore so confirm works immediately."""
    from datetime import timedelta

    from zebra_agent_web.api import agent_engine
    from zebra_agent_web.trust_store import DjangoTrustStore

    store = DjangoTrustStore(cooling_off=timedelta(0))
    monkeypatch.setattr(agent_engine, "get_trust", lambda: store)
    return store


@pytest.mark.django_db(transaction=True)
def test_freeing_endpoints_require_auth(client):
    assert client.get("/api/trust/freeing/").status_code in (302, 401, 403)
    assert client.post(
        "/api/trust/freeing/initiate/", {}, content_type="application/json"
    ).status_code in (302, 401, 403)


@pytest.mark.django_db(transaction=True)
def test_initiate_blocked_unless_all_autonomous(authenticated_client, fast_freeing):
    response = authenticated_client.post(
        "/api/trust/freeing/initiate/", {}, content_type="application/json"
    )
    assert response.status_code == 400
    assert "AUTONOMOUS" in response.json()["error"]


@pytest.mark.django_db(transaction=True)
def test_freeing_flow_initiate_confirm(authenticated_client, fast_freeing, test_user):
    import asyncio

    asyncio.run(_free_all(fast_freeing, test_user.id))

    initiate = authenticated_client.post(
        "/api/trust/freeing/initiate/", {}, content_type="application/json"
    )
    assert initiate.status_code == 200
    assert initiate.json()["state"] in ("cooling_off", "freed")

    confirm = authenticated_client.post(
        "/api/trust/freeing/confirm/", {}, content_type="application/json"
    )
    assert confirm.status_code == 200
    assert confirm.json()["state"] == "freed"

    status_resp = authenticated_client.get("/api/trust/freeing/")
    assert status_resp.json()["state"] == "freed"


@pytest.mark.django_db(transaction=True)
def test_freeing_disabled_returns_403(authenticated_client, fast_freeing, settings):
    settings.ZEBRA_DISABLE_FREEING = True

    assert authenticated_client.get("/api/trust/freeing/").status_code == 403
    assert (
        authenticated_client.post(
            "/api/trust/freeing/initiate/", {}, content_type="application/json"
        ).status_code
        == 403
    )
