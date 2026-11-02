"""The Commons owner and sphere for workflow provenance (#229)."""

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from zebra_agent.library import WorkflowLibrary
from zebra_agent_web.api.commons_owner import resolve_commons_owner

User = get_user_model()


@pytest.mark.django_db(transaction=True)
async def test_no_user_means_no_owner_yet():
    assert await resolve_commons_owner() == (None, "local")


@pytest.mark.django_db(transaction=True)
async def test_owner_defaults_to_the_first_user():
    owner = await sync_to_async(User.objects.create_user)(username="c229_owner", password="x")
    await sync_to_async(User.objects.create_user)(username="c229_smoke", password="x")
    assert await resolve_commons_owner() == (owner.id, "local")


@pytest.mark.django_db(transaction=True)
async def test_library_picks_the_owner_up_after_setup(tmp_path):
    library = WorkflowLibrary(tmp_path, owner_resolver=resolve_commons_owner)
    assert await library.refresh_owner() is None

    owner = await sync_to_async(User.objects.create_user)(username="c229_late", password="x")
    assert await library.refresh_owner() == owner.id
    assert library.sphere == "local"
