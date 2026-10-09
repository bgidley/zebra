"""/knowledge/ shows agent-learned entries and lets the user confirm them (F152)."""

import pytest
from asgiref.sync import sync_to_async
from django.http import Http404
from zebra_agent.knowledge import KnowledgeEntry
from zebra_agent_web.api import web_views
from zebra_agent_web.knowledge_store import DjangoPersonalKnowledgeStore

pytestmark = [pytest.mark.django_db(transaction=True)]


@pytest.fixture
def user(db):
    from django.contrib.auth import get_user_model
    from zebra_agent_web.api.identity import set_identity_sync

    set_identity_sync("Test User")
    return get_user_model().objects.create_user(username="knowledge-user")


@pytest.fixture
def rf(user):
    from django.test import RequestFactory

    def _make(method, path, as_user=None):
        request = getattr(RequestFactory(), method)(path, {})
        request.user = as_user or user
        request._dont_enforce_csrf_checks = True
        return request

    return _make


async def _add(user_id, key="employer", value="Acme", source="agent", confidence=0.5):
    entry = KnowledgeEntry.create(
        user_id=user_id,
        category="facts",
        key=key,
        value=value,
        source=source,
        confidence=confidence,
    )
    await DjangoPersonalKnowledgeStore().add_entry(entry)
    return entry


async def test_list_shows_source_confidence_and_confirm_for_agent_entries(user, rf):
    agent_entry = await _add(user.id)
    human_entry = await _add(user.id, key="home_city", value="York", source="human", confidence=1)

    html = (await web_views.knowledge_list(rf("get", "/knowledge/"))).content.decode()

    assert ">agent</span>" in html
    assert "0.50" in html
    assert f"/knowledge/{agent_entry.id}/confirm/" in html
    assert f"/knowledge/{human_entry.id}/confirm/" not in html


async def test_list_hides_deleted_entries(user, rf):
    entry = await _add(user.id, value="Hidden Corp")
    await DjangoPersonalKnowledgeStore().soft_delete_entry(entry.id)

    html = (await web_views.knowledge_list(rf("get", "/knowledge/"))).content.decode()
    assert "Hidden Corp" not in html


async def test_confirm_promotes_to_human_full_confidence(user, rf):
    entry = await _add(user.id)

    response = await web_views.knowledge_confirm(
        rf("post", f"/knowledge/{entry.id}/confirm/"), entry.id
    )

    assert response.status_code == 302
    confirmed = await DjangoPersonalKnowledgeStore().get_entry(entry.id)
    assert confirmed.confidence == 1.0
    assert confirmed.source == "human"
    assert confirmed.value == "Acme"


async def test_confirm_other_users_entry_is_404(user, rf):
    from django.contrib.auth import get_user_model

    other = await sync_to_async(get_user_model().objects.create_user)(username="other")
    entry = await _add(other.id)

    with pytest.raises(Http404):
        await web_views.knowledge_confirm(rf("post", "/x/"), entry.id)
    unchanged = await DjangoPersonalKnowledgeStore().get_entry(entry.id)
    assert unchanged.source == "agent"
