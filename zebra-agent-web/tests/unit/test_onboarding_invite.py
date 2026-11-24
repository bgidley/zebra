"""The signed-in "Invite a friend" page: the shareable onboarding link (#330)."""

from __future__ import annotations

from urllib.parse import urlsplit

import pytest

pytestmark = pytest.mark.django_db(transaction=True)

BASE = "https://zebra.example.com"


def _public(settings, base: str = BASE, trusted: list[str] | None = None):
    settings.ZEBRA_AGENT_SETTINGS = {**settings.ZEBRA_AGENT_SETTINGS, "PUBLIC_BASE_URL": base}
    settings.CSRF_TRUSTED_ORIGINS = trusted or []


def _link(page: str) -> str:
    return page.split('id="invite-link"', 1)[1].split('value="', 1)[1].split('"', 1)[0]


def test_invite_page_shows_the_configured_https_link(
    onboarding_env, authenticated_client, settings
):
    _public(settings)
    page = authenticated_client.get("/invite/").content.decode()
    assert _link(page) == f"{BASE}/onboarding/"
    assert "invite-copy" in page and "navigator.share" in page


def test_link_ignores_the_host_header_and_carries_no_identity(
    onboarding_env, authenticated_client, settings, test_user
):
    _public(settings)
    page = authenticated_client.get("/invite/", HTTP_HOST="evil.example.net").content.decode()
    link = urlsplit(_link(page))
    assert link.hostname == "zebra.example.com"
    assert link.query == "" and link.path == "/onboarding/"
    assert test_user.username not in page.split("<main", 1)[-1].split("invite-text")[0]


def test_userinfo_origin_is_refused(onboarding_env, authenticated_client, settings):
    _public(settings, "https://user:pw@zebra.example.com/some/path?x=1")
    page = authenticated_client.get("/invite/").content.decode()
    assert "user:pw" not in page and "invite-copy" not in page
    assert "ZEBRA_PUBLIC_BASE_URL" in page


def test_base_path_is_dropped(onboarding_env, authenticated_client, settings):
    _public(settings, "https://zebra.example.com/some/path?x=1")
    page = authenticated_client.get("/invite/").content.decode()
    assert _link(page) == f"{BASE}/onboarding/"


def test_falls_back_to_first_https_csrf_trusted_origin(
    onboarding_env, authenticated_client, settings
):
    _public(settings, "", trusted=["http://plain.example.com", "https://tunnel.example.org"])
    page = authenticated_client.get("/invite/").content.decode()
    assert _link(page) == "https://tunnel.example.org/onboarding/"


def test_no_configured_origin_shows_no_link_even_with_a_host_header(
    onboarding_env, authenticated_client, settings
):
    _public(settings, "")
    page = authenticated_client.get("/invite/", HTTP_HOST="evil.example.net").content.decode()
    assert "evil.example.net" not in page
    assert "ZEBRA_PUBLIC_BASE_URL" in page and "invite-copy" not in page


def test_http_origin_is_not_shared(onboarding_env, authenticated_client, settings):
    _public(settings, "http://zebra.example.com")
    page = authenticated_client.get("/invite/").content.decode()
    assert "invite-copy" not in page


def test_404_when_the_environment_has_onboarding_off(
    onboarding_env, authenticated_client, settings
):
    _public(settings)
    settings.ZEBRA_AGENT_SETTINGS = {**settings.ZEBRA_AGENT_SETTINGS, "ONBOARDING_ENABLED": False}
    assert authenticated_client.get("/invite/").status_code == 404


def test_404_when_the_owner_switch_is_off(onboarding_env, authenticated_client, settings):
    from zebra_agent_web.api.models import SystemStateModel

    _public(settings)
    SystemStateModel.objects.update(onboarding_enabled=False)
    assert authenticated_client.get("/invite/").status_code == 404


def test_nav_entry_present_only_when_env_enabled(onboarding_env, authenticated_client, settings):
    assert 'href="/invite/"' in authenticated_client.get("/onboarding/manage/").content.decode()
    settings.ZEBRA_AGENT_SETTINGS = {**settings.ZEBRA_AGENT_SETTINGS, "ONBOARDING_ENABLED": False}
    assert 'href="/invite/"' not in authenticated_client.get("/onboarding/manage/").content.decode()
