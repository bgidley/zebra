"""Every goal entry point stamps the submitting user onto the process (#151).

Before #151, ``POST /api/goals/`` started the Agent Main Loop without a
``__user_id__``, so consult_knowledge, the values profile and run ownership
silently fell back to "no user".
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from rest_framework.test import APIClient
from zebra_agent_web.api import views, web_views
from zebra_agent_web.api.identity import goal_identity, goal_identity_sync, set_identity_sync

User = get_user_model()


@pytest.fixture
def owner(db):
    return User.objects.create_user(username="f151_owner", password="x")


def _fake_agent_engine(result=None):
    agent_loop = MagicMock()
    agent_loop.process_goal = AsyncMock(return_value=result or MagicMock(awaiting_input=True))
    fake = MagicMock()
    fake.ensure_initialized = AsyncMock()
    fake.get_agent_loop.return_value = agent_loop
    return fake, agent_loop


def _wait_for_api_runs(timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while views._active_api_runs and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not views._active_api_runs, "background goal thread did not finish"


# --- identity helpers --------------------------------------------------------


@pytest.mark.django_db(transaction=True)
async def test_goal_identity_reads_identity_from_async_context():
    stored = await sync_to_async(set_identity_sync)("Ben")
    assert await goal_identity() == {
        "user_display_name": "Ben",
        "user_identity_id": stored["identity_id"],
    }


def test_goal_identity_sync_blank_when_unreadable():
    with patch("zebra_agent_web.api.identity.get_identity_sync", side_effect=RuntimeError):
        assert goal_identity_sync() == {"user_display_name": "", "user_identity_id": ""}


# --- POST /api/goals/ ---------------------------------------------------------


@pytest.mark.django_db
def test_api_execute_goal_runs_as_authenticated_user(owner):
    identity = set_identity_sync("Ben")
    fake, agent_loop = _fake_agent_engine()
    client = APIClient()
    client.force_authenticate(user=owner)

    with patch.object(views, "agent_engine", fake):
        response = client.post("/api/goals/", {"goal": "Summarise my notes"}, format="json")
        _wait_for_api_runs()

    assert response.status_code == 202
    agent_loop.process_goal.assert_awaited_once()
    kwargs = agent_loop.process_goal.call_args.kwargs
    assert kwargs["run_id"] == response.json()["run_id"]
    assert kwargs["user_id"] == owner.id
    assert kwargs["identity"] == {
        "user_display_name": "Ben",
        "user_identity_id": identity["identity_id"],
    }


@pytest.mark.django_db
def test_api_continue_passes_identity_to_queue_goal(owner):
    """The API continue endpoint already passed user_id; it now carries identity too."""
    set_identity_sync("Ben")
    process = MagicMock()
    process.id = "proc-1"
    process.properties = {"run_id": "new-run"}
    queue = AsyncMock(return_value=process)
    run = MagicMock(goal="g")
    metrics = MagicMock(get_run=AsyncMock(return_value=run))
    fake = MagicMock(ensure_initialized=AsyncMock())
    fake.get_metrics.return_value = metrics
    client = APIClient()
    client.force_authenticate(user=owner)

    with (
        patch.object(views, "agent_engine", fake),
        patch("zebra_agent_web.api.goals.queue_goal", queue),
        patch(
            "zebra_tasks.agent.followup.load_previous_run_context",
            AsyncMock(return_value={"run_id": "r1"}),
        ),
    ):
        response = client.post("/api/runs/r1/continue/", {"comment": "go on"}, format="json")

    assert response.status_code == 202
    assert queue.call_args.kwargs["user_id"] == owner.id
    assert queue.call_args.kwargs["identity"]["user_display_name"] == "Ben"


# --- web: /run/execute/ and the background runner -----------------------------


@pytest.mark.django_db(transaction=True)
async def test_web_execute_passes_user_and_identity(owner):
    await sync_to_async(set_identity_sync)("Ben")
    request = RequestFactory().post("/run/execute/", {"goal": "Plan my week"})
    request.user = owner
    background = AsyncMock()

    with (
        patch.object(web_views, "_execute_goal_background", background),
        patch.object(web_views, "render", return_value=MagicMock()),
    ):
        await web_views.run_goal_execute(request)
        for task in list(web_views._active_tasks.values()):
            await task

    kwargs = background.call_args.kwargs
    assert kwargs["user_id"] == owner.id
    assert kwargs["identity"]["user_display_name"] == "Ben"


async def test_execute_goal_background_hands_user_to_agent_loop():
    fake, agent_loop = _fake_agent_engine()
    channel_layer = MagicMock(group_send=AsyncMock())
    identity = {"user_display_name": "Ben", "user_identity_id": "id-1"}

    with (
        patch.object(web_views, "agent_engine", fake),
        patch.object(web_views, "get_channel_layer", return_value=channel_layer),
    ):
        await web_views._execute_goal_background("run-1", "g", user_id=7, identity=identity)

    kwargs = agent_loop.process_goal.call_args.kwargs
    assert kwargs["user_id"] == 7
    assert kwargs["identity"] == identity


@pytest.mark.django_db(transaction=True)
async def test_web_queue_passes_identity(owner):
    await sync_to_async(set_identity_sync)("Ben")
    request = RequestFactory().post("/run/queue/", {"goal": "Plan my week", "priority": "2"})
    request.user = owner
    process = MagicMock()
    process.id = "proc-1234567890ab"
    queue = AsyncMock(return_value=process)

    with patch("zebra_agent_web.api.goals.queue_goal", queue):
        response = await web_views.run_goal_queue(request)

    assert response.status_code == 200
    assert queue.call_args.kwargs["user_id"] == owner.id
    assert queue.call_args.kwargs["identity"]["user_display_name"] == "Ben"


# --- CLI ------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
async def test_cli_goal_runs_as_named_user(owner):
    from zebra_agent_web.cli import _goal_async

    fake, agent_loop = _fake_agent_engine(
        MagicMock(run_id="r", workflow_name="W", success=True, tokens_used=0, error=None, output="")
    )
    agent_loop.provider_name = "anthropic"
    with (
        patch("zebra_agent_web.api.agent_engine.ensure_initialized", fake.ensure_initialized),
        patch("zebra_agent_web.api.agent_engine.get_agent_loop", fake.get_agent_loop),
    ):
        code = await _goal_async("hi", model="haiku", queue=False, priority=3, user="f151_owner")

    assert code == 0
    assert agent_loop.process_goal.call_args.kwargs["user_id"] == owner.id
    assert "identity" in agent_loop.process_goal.call_args.kwargs


@pytest.mark.django_db(transaction=True)
async def test_cli_unknown_user_exits_with_error(capsys):
    from zebra_agent_web.cli import _goal_async

    code = await _goal_async("hi", model="haiku", queue=True, priority=3, user="nobody")

    assert code == 2
    assert "nobody" in capsys.readouterr().err
