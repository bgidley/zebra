"""Activity page never shows stale data (#272).

Covers the three causes: cacheable HTML responses, back/forward-cache
snapshots, and an activity list that stopped polling once nothing ran.
"""

from __future__ import annotations

import re

import pytest
from django.contrib.auth import get_user_model
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.test import Client, RequestFactory
from zebra_agent_web.middleware import NoStoreHtmlMiddleware

# ---------------------------------------------------------------------------
# NoStoreHtmlMiddleware
# ---------------------------------------------------------------------------


def _through_middleware(response: HttpResponse) -> HttpResponse:
    return NoStoreHtmlMiddleware(lambda request: response)(RequestFactory().get("/activity/"))


def test_html_response_is_not_stored_and_varies_on_htmx():
    response = _through_middleware(HttpResponse("<p>hi</p>"))

    assert "no-store" in response["Cache-Control"]
    assert "private" in response["Cache-Control"]
    assert "HX-Request" in response["Vary"]


def test_own_cache_control_is_kept():
    original = HttpResponse("<p>hi</p>")
    original["Cache-Control"] = "max-age=60"

    response = _through_middleware(original)

    assert response["Cache-Control"] == "max-age=60"


def test_json_response_is_untouched():
    response = _through_middleware(JsonResponse({"ok": True}))

    assert not response.has_header("Cache-Control")


async def test_async_path_marks_html_uncacheable():
    async def get_response(request):
        return HttpResponse("<p>hi</p>")

    response = await NoStoreHtmlMiddleware(get_response)(RequestFactory().get("/"))

    assert "no-store" in response["Cache-Control"]


@pytest.mark.django_db
def test_middleware_is_installed():
    user = get_user_model().objects.create_user(username="fresh")
    client = Client()
    client.force_login(user)

    response = client.get("/auth/login/")

    assert "no-store" in response["Cache-Control"]
    assert "HX-Request" in response["Vary"]


# ---------------------------------------------------------------------------
# Activity list polling
# ---------------------------------------------------------------------------


def _trigger(**context) -> str:
    base = {"groups": [], "human_only": True, "show_completed": False, "group_by": "status"}
    html = render_to_string("partials/activity_list.html", {**base, **context})
    match = re.search(r'hx-trigger="([^"]*)"', html)
    assert match, "activity list must always poll"
    return match.group(1)


def test_polls_fast_while_running():
    assert _trigger(has_running=True, has_queued=False).startswith("every 5s")


def test_polls_fast_while_queued():
    assert _trigger(has_running=False, has_queued=True).startswith("every 5s")


def test_keeps_polling_when_idle():
    assert _trigger(has_running=False, has_queued=False).startswith("every 30s")


def test_refreshes_when_tab_becomes_visible():
    assert "visibilitychange" in _trigger(has_running=False, has_queued=False)


# ---------------------------------------------------------------------------
# Back/forward cache
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_base_reloads_pages_restored_from_bfcache():
    user = get_user_model().objects.create_user(username="bf")
    request = RequestFactory().get("/activity/")
    request.user = user

    html = render_to_string("base.html", {"user": user}, request=request)

    assert "pageshow" in html
    assert "persisted" in html
