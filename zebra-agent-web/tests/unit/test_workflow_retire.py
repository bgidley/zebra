"""Retire and restore workflows from the web UI (#148)."""

import pytest
from zebra_agent.library import WorkflowLibrary
from zebra_agent.metrics import WorkflowStats
from zebra_agent_web.api import web_views

pytestmark = [pytest.mark.django_db(transaction=True)]

_YAML = """name: "Old Search"
description: "Searches the web"
tags: ["web"]
first_task: a
tasks:
  a:
    name: A
    action: llm_call
    properties:
      prompt: hi
routings: []
"""


class _Metrics:
    async def get_stats(self, name):
        return WorkflowStats(workflow_name=name)

    async def get_all_stats(self):
        return []


@pytest.fixture
def library(tmp_path, monkeypatch):
    import zebra_agent_web.api.agent_engine as agent_engine_module

    library = WorkflowLibrary(tmp_path / "workflows")
    library.add_workflow(_YAML)

    async def _noop():
        return None

    monkeypatch.setattr(agent_engine_module, "ensure_initialized", _noop)
    monkeypatch.setattr(agent_engine_module, "get_library", lambda: library)
    monkeypatch.setattr(agent_engine_module, "get_metrics", lambda: _Metrics())
    return library


@pytest.fixture
def rf(db):
    from django.contrib.auth import get_user_model
    from django.test import RequestFactory
    from zebra_agent_web.api.identity import set_identity_sync

    set_identity_sync("Test User")
    user = get_user_model().objects.create_user(username="retire-user")

    def _make(method, path, data=None, htmx=False):
        headers = {"HX-Request": "true"} if htmx else {}
        request = getattr(RequestFactory(), method)(path, data or {}, headers=headers)
        request.user = user
        request._dont_enforce_csrf_checks = True
        return request

    return _make


async def test_retire_hides_workflow_and_library_page_lists_it(library, rf):
    response = await web_views.workflow_retire(
        rf("post", "/workflows/Old Search/retire/", {"reason": "replaced"}, htmx=True),
        "Old Search",
    )
    assert response.status_code == 204
    assert response["HX-Redirect"] == "/workflows/"
    assert await library.list_workflows() == []

    page = await web_views.workflow_library(rf("get", "/workflows/"))
    html = page.content.decode()
    assert "Retired workflows" in html
    assert "replaced" in html
    assert 'hx-post="/workflows/Old Search/restore/"' in html


async def test_retired_workflow_detail_shows_banner_and_restore(library, rf):
    library.retire("Old Search", "LLM-defined workflow not used since 2026-01-01")

    response = await web_views.workflow_detail(rf("get", "/workflows/Old Search/"), "Old Search")
    html = response.content.decode()

    assert response.status_code == 200
    assert "not used since 2026-01-01" in html
    assert "/workflows/Old Search/restore/" in html
    assert "/workflows/Old Search/retire/" not in html


async def test_restore_returns_workflow_to_library(library, rf):
    library.retire("Old Search", "unused")

    response = await web_views.workflow_restore(
        rf("post", "/workflows/Old Search/restore/", htmx=True), "Old Search"
    )

    assert response.status_code == 204
    assert [w.name for w in await library.list_workflows()] == ["Old Search"]


async def test_retire_unknown_workflow_is_404(library, rf):
    response = await web_views.workflow_retire(rf("post", "/workflows/Nope/retire/"), "Nope")

    assert response.status_code == 404


async def test_library_page_without_retired_has_no_section(library, rf):
    page = await web_views.workflow_library(rf("get", "/workflows/"))

    assert "Retired workflows" not in page.content.decode()
