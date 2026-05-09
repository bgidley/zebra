"""Tests for the ethics audit log API (REQ-ETH-006 / F20)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from rest_framework.test import APIClient
from zebra_agent.storage.ethics_audit import InMemoryEthicsAuditStore
from zebra_agent.storage.interfaces import EthicsAuditEntry


def _make_entry(**kwargs) -> EthicsAuditEntry:
    defaults = {
        "process_id": "proc-1",
        "goal": "help me do something",
        "approved": True,
        "overall_reasoning": "Passes Kantian tests",
        "check_type": "kantian",
        "evaluated_at": datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC),
    }
    defaults.update(kwargs)
    return EthicsAuditEntry(**defaults)


def _build_store(*entries: EthicsAuditEntry) -> InMemoryEthicsAuditStore:
    """Create a populated in-memory store."""
    store = InMemoryEthicsAuditStore()
    asyncio.run(store.initialize())
    for e in entries:
        asyncio.run(store.append(e))
    return store


def _patch_store(store: InMemoryEthicsAuditStore):
    """Return context managers to patch agent_engine with the given store."""
    return [
        patch(
            "zebra_agent_web.api.views.agent_engine.ensure_initialized",
            new_callable=AsyncMock,
        ),
        patch(
            "zebra_agent_web.api.views.agent_engine.get_ethics_audit",
            return_value=store,
        ),
    ]


@pytest.mark.django_db(transaction=True)
class TestEthicsAuditListAPI:
    """Tests for GET /api/ethics-audit/."""

    @pytest.fixture(autouse=True)
    def setup_clients(self, test_user):
        self.staff_user = test_user
        self.staff_user.is_staff = True
        self.staff_user.save()

        non_staff_user_class = self.staff_user.__class__
        self.non_staff = non_staff_user_class.objects.create_user(username="pleb")

        self.staff_client = APIClient()
        self.staff_client.force_authenticate(user=self.staff_user)

        self.anon_client = APIClient()

        self.non_staff_client = APIClient()
        self.non_staff_client.force_authenticate(user=self.non_staff)

    def test_unauthenticated_returns_403(self):
        store = _build_store()
        with _patch_store(store)[0], _patch_store(store)[1]:
            response = self.anon_client.get("/api/ethics-audit/")
        assert response.status_code == 403

    def test_non_staff_returns_403(self):
        store = _build_store()
        with _patch_store(store)[0], _patch_store(store)[1]:
            response = self.non_staff_client.get("/api/ethics-audit/")
        assert response.status_code == 403

    def test_list_all(self):
        e1 = _make_entry(goal="first")
        e2 = _make_entry(goal="second")
        store = _build_store(e1, e2)
        patches = _patch_store(store)
        with patches[0], patches[1]:
            response = self.staff_client.get("/api/ethics-audit/")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2

    def test_filter_approved_true(self):
        yes = _make_entry(approved=True, goal="approved goal")
        no = _make_entry(approved=False, goal="rejected goal")
        store = _build_store(yes, no)
        patches = _patch_store(store)
        with patches[0], patches[1]:
            response = self.staff_client.get("/api/ethics-audit/?approved=true")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["results"][0]["approved"] is True

    def test_filter_approved_false(self):
        yes = _make_entry(approved=True, goal="approved goal")
        no = _make_entry(approved=False, goal="rejected goal")
        store = _build_store(yes, no)
        patches = _patch_store(store)
        with patches[0], patches[1]:
            response = self.staff_client.get("/api/ethics-audit/?approved=false")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["results"][0]["approved"] is False

    def test_filter_by_date_range(self):
        jan = _make_entry(evaluated_at=datetime(2026, 1, 15, tzinfo=UTC))
        may = _make_entry(evaluated_at=datetime(2026, 5, 1, tzinfo=UTC))
        store = _build_store(jan, may)
        patches = _patch_store(store)
        with patches[0], patches[1]:
            response = self.staff_client.get("/api/ethics-audit/?from_date=2026-05-01")
        assert response.status_code == 200
        assert response.json()["count"] == 1

    def test_csv_export(self):
        e = _make_entry(goal="test export")
        store = _build_store(e)
        patches = _patch_store(store)
        with patches[0], patches[1]:
            response = self.staff_client.get("/api/ethics-audit/?export=csv")
        assert response.status_code == 200
        assert "text/csv" in response["Content-Type"]
        assert "ethics-audit.csv" in response["Content-Disposition"]
        content = response.content.decode()
        assert "test export" in content

    def test_delete_returns_405(self):
        store = _build_store()
        patches = _patch_store(store)
        with patches[0], patches[1]:
            response = self.staff_client.delete("/api/ethics-audit/some-id/")
        assert response.status_code == 405


@pytest.mark.django_db(transaction=True)
class TestEthicsAuditDetailAPI:
    """Tests for GET /api/ethics-audit/<id>/."""

    @pytest.fixture(autouse=True)
    def setup_client(self, test_user):
        test_user.is_staff = True
        test_user.save()
        self.client = APIClient()
        self.client.force_authenticate(user=test_user)

    def test_get_existing_entry(self):
        e = _make_entry(goal="some goal")
        store = _build_store(e)
        patches = _patch_store(store)
        with patches[0], patches[1]:
            response = self.client.get(f"/api/ethics-audit/{e.id}/")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == e.id
        assert data["goal"] == "some goal"

    def test_get_missing_entry_returns_404(self):
        store = _build_store()
        patches = _patch_store(store)
        with patches[0], patches[1]:
            response = self.client.get("/api/ethics-audit/does-not-exist/")
        assert response.status_code == 404
