"""Tests for F4 single-user identity — helpers, setup view, middleware."""

from __future__ import annotations

import asyncio

import pytest
from rest_framework.test import APIClient

# ---------------------------------------------------------------------------
# Identity helpers
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestIdentityHelpers:
    def test_default_not_setup(self):
        from zebra_agent_web.api.identity import get_identity_sync, is_setup_complete_sync

        assert not is_setup_complete_sync()
        identity = get_identity_sync()
        assert identity["display_name"] == ""
        assert identity["setup_completed"] is False

    def test_set_identity_creates_uuid(self):
        from zebra_agent_web.api.identity import get_identity_sync, set_identity_sync

        set_identity_sync("Ben")
        identity = get_identity_sync()
        assert identity["display_name"] == "Ben"
        assert len(identity["identity_id"]) == 36  # UUID
        assert identity["setup_completed"] is True

    def test_identity_id_never_changes(self):
        from zebra_agent_web.api.identity import get_identity_sync, set_identity_sync

        set_identity_sync("Alice")
        first_id = get_identity_sync()["identity_id"]
        set_identity_sync("Bob")  # rename
        assert get_identity_sync()["identity_id"] == first_id

    def test_display_name_stripped(self):
        from zebra_agent_web.api.identity import get_identity_sync, set_identity_sync

        set_identity_sync("  Ben  ")
        assert get_identity_sync()["display_name"] == "Ben"

    def test_is_setup_complete_after_set(self):
        from zebra_agent_web.api.identity import is_setup_complete_sync, set_identity_sync

        set_identity_sync("Ben")
        assert is_setup_complete_sync() is True

    def test_async_roundtrip(self):
        from zebra_agent_web.api.identity import get_identity, is_setup_complete, set_identity

        async def _run():
            await set_identity("Async Ben")
            assert await is_setup_complete() is True
            identity = await get_identity()
            assert identity["display_name"] == "Async Ben"

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Setup view (GET + POST)
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestSetupView:
    @pytest.fixture(autouse=True)
    def reset_identity(self):
        from zebra_agent_web.api.models import SystemStateModel

        SystemStateModel.objects.filter(pk=1).update(
            setup_completed=False, user_display_name="", user_identity_id=""
        )
        yield
        SystemStateModel.objects.filter(pk=1).update(
            setup_completed=False, user_display_name="", user_identity_id=""
        )

    def test_get_renders_form(self):
        client = APIClient()
        response = client.get("/setup/")
        assert response.status_code == 200
        assert b"display_name" in response.content

    def test_post_valid_redirects_to_root(self):
        client = APIClient()
        response = client.post("/setup/", {"display_name": "Ben"})
        assert response.status_code == 302
        assert response["Location"] == "/"

    def test_post_empty_name_shows_error(self):
        client = APIClient()
        response = client.post("/setup/", {"display_name": "   "})
        assert response.status_code == 200
        assert b"display_name" in response.content

    def test_post_stores_identity(self):
        from zebra_agent_web.api.identity import get_identity_sync

        client = APIClient()
        client.post("/setup/", {"display_name": "Ben"})
        assert get_identity_sync()["display_name"] == "Ben"
        assert get_identity_sync()["setup_completed"] is True


# ---------------------------------------------------------------------------
# Middleware redirect
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestSetupRequiredMiddleware:
    @pytest.fixture(autouse=True)
    def reset_identity(self):
        from zebra_agent_web.api.models import SystemStateModel

        SystemStateModel.objects.filter(pk=1).update(
            setup_completed=False, user_display_name="", user_identity_id=""
        )
        yield
        SystemStateModel.objects.filter(pk=1).update(
            setup_completed=True, user_display_name="Test", user_identity_id="test-id"
        )

    def test_root_redirects_to_setup_when_not_configured(self):
        client = APIClient()
        response = client.get("/")
        assert response.status_code == 302
        assert response["Location"] == "/setup/"

    def test_api_health_exempt_from_redirect(self):
        from unittest.mock import AsyncMock, patch

        client = APIClient()
        with (
            patch("zebra_agent_web.api.views.agent_engine") as mock_ae,
            patch("zebra_agent_web.api.views.engine") as mock_eng,
        ):
            mock_ae.ensure_initialized = AsyncMock()
            mock_store = AsyncMock()
            mock_store.count_processes_by_state = AsyncMock(return_value=0)
            mock_eng.get_engine.return_value.store = mock_store
            response = client.get("/api/health/")
        assert response.status_code == 200

    def test_setup_page_exempt_from_redirect(self):
        client = APIClient()
        response = client.get("/setup/")
        assert response.status_code == 200  # not a redirect loop

    def test_no_redirect_when_setup_complete(self):
        from zebra_agent_web.api.identity import set_identity_sync

        set_identity_sync("Ben")
        client = APIClient()
        response = client.get("/setup/")
        assert response.status_code == 200
