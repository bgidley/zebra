"""Scheduled routine goals are queued through queue_goal as the owner (F155)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from zebra_agent.scheduler.routine import Routine
from zebra_agent_web.api.daemon import queue_routine_goal, resolve_routine_user
from zebra_agent_web.api.identity import set_identity_sync

User = get_user_model()

NEWS = Routine(
    name="daily_news_reading",
    schedule="0 7 * * *",
    goal="Read today's news",
    workflow="Daily News Reading",
    goal_priority=2,
)


@pytest.fixture
def users(db):
    plain = User.objects.create_user(username="f155_plain", password="x")
    owner = User.objects.create_superuser(username="f155_owner", password="x")
    User.objects.create_superuser(username="f155_later_admin", password="x")
    User.objects.create_superuser(username="f155_inactive", password="x", is_active=False)
    return {"plain": plain, "owner": owner}


@pytest.mark.django_db(transaction=True)
async def test_default_user_is_first_active_superuser(users):
    assert await resolve_routine_user(None) == users["owner"].id


@pytest.mark.django_db(transaction=True)
async def test_run_as_names_the_user(users):
    assert await resolve_routine_user("f155_plain") == users["plain"].id


@pytest.mark.django_db(transaction=True)
async def test_unknown_or_inactive_user_runs_without_user(users):
    assert await resolve_routine_user("nobody") is None
    assert await resolve_routine_user("f155_inactive") is None


@pytest.mark.django_db(transaction=True)
async def test_queue_routine_goal_passes_routine_properties(users):
    await sync_to_async(set_identity_sync)("Ben")
    queue_goal = AsyncMock(return_value=MagicMock(id="proc-1"))

    with patch("zebra_agent_web.api.goals.queue_goal", queue_goal):
        await queue_routine_goal(NEWS)

    queue_goal.assert_awaited_once()
    call = queue_goal.call_args
    assert call.args == ("Read today's news",)
    assert call.kwargs["priority"] == 2
    assert call.kwargs["user_id"] == users["owner"].id
    assert call.kwargs["identity"]["user_display_name"] == "Ben"
    assert call.kwargs["extra_properties"] == {
        "__routine__": "daily_news_reading",
        "requested_workflow": "Daily News Reading",
    }


async def test_queue_goal_extra_properties_never_override_core_keys():
    from zebra_agent_web.api.goals import queue_goal

    library = MagicMock()
    library.list_workflows = AsyncMock(return_value=[])
    wf_engine = MagicMock()
    wf_engine.create_process = AsyncMock()

    with (
        patch("zebra_agent_web.api.agent_engine.ensure_initialized", new=AsyncMock()),
        patch("zebra_agent_web.api.engine.ensure_initialized", new=AsyncMock()),
        patch("zebra_agent_web.api.agent_engine.get_library", return_value=library),
        patch("zebra_agent_web.api.engine.get_engine", return_value=wf_engine),
    ):
        await queue_goal(
            "Read the news",
            user_id=7,
            extra_properties={"__routine__": "r", "goal": "hijack", "__user_id__": 99},
        )

    props = wf_engine.create_process.call_args.kwargs["properties"]
    assert props["__routine__"] == "r"
    assert props["goal"] == "Read the news"
    assert props["__user_id__"] == 7
