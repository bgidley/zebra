"""Tests for the kill-switch feature (F2 / REQ-TRUST-007).

Tests are split into:
- Unit tests for kill_switch helpers (using Django's test DB via pytest-django)
- API tests for GET/POST /api/kill-switch/
- Daemon _tick() tests verifying halted guard
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from rest_framework.test import APIClient

# ---------------------------------------------------------------------------
# Kill-switch helper tests (Django DB)
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestKillSwitchHelpers:
    def test_default_not_halted(self):
        from zebra_agent_web.api.kill_switch import get_status_sync

        info = get_status_sync()
        assert info["halted"] is False
        assert info["halted_at"] is None
        assert info["halted_reason"] == ""

    def test_halt_sets_flag(self):
        from zebra_agent_web.api.kill_switch import get_status_sync, set_halted_sync

        set_halted_sync(True, reason="maintenance")
        info = get_status_sync()
        assert info["halted"] is True
        assert info["halted_at"] is not None
        assert info["halted_reason"] == "maintenance"

    def test_resume_clears_flag(self):
        from zebra_agent_web.api.kill_switch import set_halted_sync

        set_halted_sync(True, reason="test")
        info = set_halted_sync(False)
        assert info["halted"] is False
        assert info["halted_at"] is None
        assert info["halted_reason"] == ""

    def test_is_halted_sync(self):
        from zebra_agent_web.api.kill_switch import is_halted_sync, set_halted_sync

        set_halted_sync(False)
        assert is_halted_sync() is False
        set_halted_sync(True)
        assert is_halted_sync() is True

    def test_singleton_pk1(self):
        """Repeated calls must not create extra rows."""
        from zebra_agent_web.api.kill_switch import set_halted_sync
        from zebra_agent_web.api.models import SystemStateModel

        set_halted_sync(True)
        set_halted_sync(False)
        assert SystemStateModel.objects.count() == 1


# ---------------------------------------------------------------------------
# Async helper tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestKillSwitchAsync:
    def test_async_roundtrip(self):
        from zebra_agent_web.api.kill_switch import get_status, is_halted, set_halted

        async def _run():
            await set_halted(True, reason="async test")
            assert await is_halted() is True
            info = await get_status()
            assert info["halted"] is True
            assert info["halted_reason"] == "async test"

            await set_halted(False)
            assert await is_halted() is False

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# REST API tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestKillSwitchAPI:
    @pytest.fixture(autouse=True)
    def reset_flag(self):
        from zebra_agent_web.api.kill_switch import set_halted_sync

        set_halted_sync(False)
        yield
        set_halted_sync(False)

    def test_get_returns_status(self):
        client = APIClient()
        response = client.get("/api/kill-switch/")
        assert response.status_code == 200
        data = response.json()
        assert "halted" in data
        assert data["halted"] is False

    def test_post_halt(self):
        client = APIClient()
        response = client.post(
            "/api/kill-switch/", {"halted": True, "reason": "test halt"}, format="json"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["halted"] is True
        assert data["halted_reason"] == "test halt"
        assert data["halted_at"] is not None

    def test_post_resume(self):
        from zebra_agent_web.api.kill_switch import set_halted_sync

        set_halted_sync(True, reason="initial")
        client = APIClient()
        response = client.post("/api/kill-switch/", {"halted": False}, format="json")
        assert response.status_code == 200
        assert response.json()["halted"] is False

    def test_post_invalid_body(self):
        client = APIClient()
        response = client.post("/api/kill-switch/", {"halted": "yes"}, format="json")
        assert response.status_code == 400

    def test_get_after_halt_reflects_state(self):
        client = APIClient()
        client.post("/api/kill-switch/", {"halted": True}, format="json")
        response = client.get("/api/kill-switch/")
        assert response.json()["halted"] is True


# ---------------------------------------------------------------------------
# Daemon _tick() tests
# ---------------------------------------------------------------------------


class TestDaemonKillSwitchGuard:
    """Verify _tick() respects the kill switch without a real DB."""

    def _make_mocks(self):
        scheduler = AsyncMock()
        budget_manager = AsyncMock()
        budget_manager.get_status = AsyncMock(
            return_value={"available": 10.0, "spent_today": 0.0, "paced_allowance": 50.0}
        )
        engine = AsyncMock()
        return scheduler, budget_manager, engine

    def test_tick_skips_when_halted(self):
        """_tick() returns early without calling scheduler when halted."""
        from zebra_agent_web.api.daemon import _tick

        scheduler, budget_manager, engine = self._make_mocks()

        async def _run():
            with patch(
                "zebra_agent_web.api.kill_switch.is_halted",
                new=AsyncMock(return_value=True),
            ):
                await _tick(
                    scheduler=scheduler,
                    budget_manager=budget_manager,
                    engine=engine,
                    dry_run=False,
                )

        asyncio.run(_run())
        scheduler.pick_next.assert_not_called()

    def test_tick_proceeds_when_not_halted_empty_queue(self):
        """_tick() calls pick_next when not halted, returns on empty queue."""
        from zebra_agent_web.api.daemon import _tick

        scheduler, budget_manager, engine = self._make_mocks()
        scheduler.pick_next = AsyncMock(return_value=None)

        async def _run():
            with patch(
                "zebra_agent_web.api.kill_switch.is_halted",
                new=AsyncMock(return_value=False),
            ):
                await _tick(
                    scheduler=scheduler,
                    budget_manager=budget_manager,
                    engine=engine,
                    dry_run=False,
                )

        asyncio.run(_run())
        scheduler.pick_next.assert_called_once()
