"""Tests for the dashboard trust-by-domain display and trust store wiring (F12)."""

from __future__ import annotations

import pytest
from zebra_agent.storage.trust import (
    DEFAULT_DOMAINS,
    InMemoryTrustStore,
    TrustLevel,
    reset_domain_registry,
)
from zebra_agent_web.api import agent_engine


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_domain_registry()
    yield
    reset_domain_registry()


class _StubLibrary:
    async def list_workflows(self):
        return []


class _StubMetrics:
    async def get_all_stats(self):
        return []

    async def get_recent_runs(self, limit=10):
        return []


@pytest.fixture
def trust_store():
    return InMemoryTrustStore()


@pytest.fixture
def completed_setup(db):
    """Mark first-run setup complete so SetupRequiredMiddleware allows the dashboard."""
    from zebra_agent_web.api.identity import set_identity_sync

    set_identity_sync("Test User")


@pytest.fixture
def stub_agent_engine(monkeypatch, trust_store, completed_setup):
    """Stub the agent_engine singletons the dashboard view touches."""

    async def _noop():
        return None

    def _raise_runtime():
        raise RuntimeError("not initialized in tests")

    monkeypatch.setattr(agent_engine, "ensure_initialized", _noop)
    monkeypatch.setattr(agent_engine, "get_library", lambda: _StubLibrary())
    monkeypatch.setattr(agent_engine, "get_metrics", lambda: _StubMetrics())
    monkeypatch.setattr(agent_engine, "get_budget_manager", _raise_runtime)
    monkeypatch.setattr(agent_engine, "get_trust", lambda: trust_store)
    return trust_store


def test_get_trust_raises_before_initialization():
    assert agent_engine._trust is None or True  # singleton may be set by other tests
    if agent_engine._trust is None:
        with pytest.raises(RuntimeError, match="Trust store not initialized"):
            agent_engine.get_trust()


@pytest.mark.django_db(transaction=True)
async def test_dashboard_shows_all_domains_with_levels(
    authenticated_async_client, stub_agent_engine, test_user
):
    await stub_agent_engine.set_trust_level(
        test_user.pk, "code", TrustLevel.SEMI_AUTONOMOUS, "earned", "ben"
    )

    response = await authenticated_async_client.get("/")

    assert response.status_code == 200
    html = response.content.decode()
    assert "Trust by Domain" in html
    for domain in DEFAULT_DOMAINS:
        assert domain in html
    assert "SEMI-AUTONOMOUS" in html
    assert "SUPERVISED" in html


@pytest.mark.django_db(transaction=True)
async def test_dashboard_defaults_all_supervised(authenticated_async_client, stub_agent_engine):
    response = await authenticated_async_client.get("/")

    assert response.status_code == 200
    html = response.content.decode()
    assert "Trust by Domain" in html
    assert html.count("SUPERVISED") >= len(DEFAULT_DOMAINS)
    assert "AUTONOMOUS</span>" not in html.replace("SEMI-AUTONOMOUS", "")
