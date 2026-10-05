"""Tests for continuing a finished run with a progress comment (F134)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import RequestFactory
from rest_framework.test import APIClient
from zebra_agent_web.api import web_views
from zebra_agent_web.api.models import TaskExecutionModel, WorkflowRunModel
from zebra_agent_web.metrics_store import DjangoMetricsStore
from zebra_agent_web.middleware import _current_user_id_var

User = get_user_model()


@pytest.fixture
def user_a(db):
    return User.objects.create_user(username="f134_user_a", password="x")


@pytest.fixture
def user_b(db):
    return User.objects.create_user(username="f134_user_b", password="x")


def _create_run_sync(
    run_id: str,
    user_id: int | None,
    *,
    success: bool = True,
    completed: bool = True,
    extends: str | None = None,
    comment: str | None = None,
    minutes_ago: int = 0,
):
    ts = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    WorkflowRunModel.objects.create(
        id=run_id,
        workflow_name="Research",
        goal=f"goal of {run_id}",
        output=f"output of {run_id}",
        error=None if success else "it broke",
        started_at=ts,
        completed_at=ts if completed else None,
        success=success,
        user_id=user_id,
        extends_run_id=extends,
        continuation_comment=comment,
    )


_create_run = sync_to_async(_create_run_sync)


@sync_to_async
def _add_task(run_id: str, order: int, state: str, output: str = "", error: str = ""):
    TaskExecutionModel.objects.create(
        id=f"{run_id}-t{order}",
        run_id=run_id,
        task_definition_id=f"step_{order}",
        task_name=f"Step {order}",
        execution_order=order,
        state=state,
        started_at=datetime.now(UTC),
        output=output or None,
        error=error or None,
    )


@pytest.fixture
def fake_agent_engine():
    """Point web_views at a real DjangoMetricsStore without initialising the agent."""
    fake = MagicMock()
    fake.ensure_initialized = AsyncMock()
    fake.get_metrics.return_value = DjangoMetricsStore()
    with patch.object(web_views, "agent_engine", fake):
        yield fake


class _AsUser:
    def __init__(self, user):
        self.user = user

    def __enter__(self):
        self.token = _current_user_id_var.set(self.user.id)

    def __exit__(self, *exc):
        _current_user_id_var.reset(self.token)


def _post(run_id: str, user, **data):
    request = RequestFactory().post(f"/runs/{run_id}/continue/", data)
    request.user = user
    return request


# --- web view: run_continue --------------------------------------------------


@pytest.mark.django_db(transaction=True)
async def test_continue_requires_comment(user_a, fake_agent_engine):
    await _create_run("f134-r1", user_a.id)
    with _AsUser(user_a):
        response = await web_views.run_continue(_post("f134-r1", user_a, comment="  "), "f134-r1")
    assert response.status_code == 400


@pytest.mark.django_db(transaction=True)
async def test_continue_404_for_other_users_or_unfinished_run(user_a, user_b, fake_agent_engine):
    await _create_run("f134-theirs", user_b.id)
    await _create_run("f134-running", user_a.id, completed=False)
    with _AsUser(user_a):
        theirs = await web_views.run_continue(
            _post("f134-theirs", user_a, comment="go on"), "f134-theirs"
        )
        running = await web_views.run_continue(
            _post("f134-running", user_a, comment="go on"), "f134-running"
        )
    assert theirs.status_code == 404
    assert running.status_code == 404


@pytest.mark.django_db(transaction=True)
async def test_continue_blank_comment_on_other_users_run_is_404(user_a, user_b, fake_agent_engine):
    await _create_run("f134-theirs-blank", user_b.id)
    with _AsUser(user_a):
        response = await web_views.run_continue(
            _post("f134-theirs-blank", user_a, comment=""), "f134-theirs-blank"
        )
    assert response.status_code == 404


@pytest.mark.django_db(transaction=True)
async def test_continue_now_starts_background_run_with_comment_and_progress(
    user_a, fake_agent_engine
):
    await _create_run("f134-failed", user_a.id, success=False)
    await _add_task("f134-failed", 1, "complete", output="2 sources")
    await _add_task("f134-failed", 2, "failed", error="timeout")
    background = AsyncMock()

    with (
        _AsUser(user_a),
        patch.object(web_views, "_execute_goal_background", background),
        patch.object(web_views, "render", return_value=MagicMock()) as render,
    ):
        await web_views.run_continue(
            _post("f134-failed", user_a, comment="Get 3 more sources", mode="now"),
            "f134-failed",
        )
        # let the created task run
        for task in list(web_views._active_tasks.values()):
            await task

    args, kwargs = background.call_args
    new_run_id, goal = args
    assert new_run_id != "f134-failed"
    assert goal == "goal of f134-failed"
    assert kwargs["continuation_comment"] == "Get 3 more sources"
    ctx = kwargs["previous_run_context"]
    assert ctx["run_id"] == "f134-failed"
    assert ctx["success"] is False
    assert [t["state"] for t in ctx["tasks"]] == ["complete", "failed"]
    assert render.call_args.args[2]["run_id"] == new_run_id


@pytest.mark.django_db(transaction=True)
async def test_continue_queue_hands_continuation_to_queue_goal(user_a, fake_agent_engine):
    await _create_run("f134-root", user_a.id, minutes_ago=10)
    await _create_run("f134-mid", user_a.id, extends="f134-root", comment="first nudge")
    process = MagicMock()
    process.id = "proc-1234567890ab"
    queue = AsyncMock(return_value=process)

    with _AsUser(user_a), patch("zebra_agent_web.api.goals.queue_goal", queue):
        response = await web_views.run_continue(
            _post("f134-mid", user_a, comment="second nudge", mode="queue", priority="2"),
            "f134-mid",
        )

    assert response.status_code == 200
    assert b"Goal Queued" in response.content
    kwargs = queue.call_args.kwargs
    assert queue.call_args.args[0] == "goal of f134-mid"
    assert kwargs["priority"] == 2
    assert kwargs["continuation_comment"] == "second nudge"
    assert kwargs["previous_run_context"]["comment"] == "first nudge"
    assert [c["run_id"] for c in kwargs["previous_run_context"]["chain"]] == ["f134-root"]


# --- chain display -----------------------------------------------------------


@pytest.mark.django_db(transaction=True)
async def test_run_chain_visible_from_original_and_continuation(user_a):
    await _create_run("f134-c0", user_a.id, minutes_ago=30)
    await _create_run("f134-c1", user_a.id, extends="f134-c0", comment="more", minutes_ago=20)
    await _create_run("f134-c2", user_a.id, extends="f134-c1", comment="finish", minutes_ago=10)
    await _create_run("f134-other", user_a.id, minutes_ago=5)
    store = DjangoMetricsStore()

    with _AsUser(user_a):
        root = await store.get_run("f134-c0")
        mid = await store.get_run("f134-c1")
        lone = await store.get_run("f134-other")
        from_root = await web_views._run_chain(store, root)
        from_mid = await web_views._run_chain(store, mid)
        from_lone = await web_views._run_chain(store, lone)

    assert [link["id"] for link in from_root] == ["f134-c0", "f134-c1", "f134-c2"]
    assert [link["id"] for link in from_mid] == ["f134-c0", "f134-c1", "f134-c2"]
    assert [link["is_current"] for link in from_mid] == [False, True, False]
    assert from_mid[2]["comment"] == "finish"
    assert from_lone == []


def test_run_chain_partial_renders_links_and_comments():
    chain = [
        {"id": "a", "position": 0, "workflow_name": "Research", "success": True,
         "started_at": datetime.now(UTC), "is_current": False, "comment": None,
         "decision": None, "rationale": None},
        {"id": "b", "position": 1, "workflow_name": "Summarise", "success": False,
         "started_at": datetime.now(UTC), "is_current": True, "comment": "keep going",
         "decision": "existing_workflow", "rationale": "summary step missing"},
    ]  # fmt: skip
    html = render_to_string("partials/run_chain.html", {"run_chain": chain})

    assert "Continuation Chain" in html
    assert 'href="/runs/a/"' in html
    assert "Continuation 1" in html
    assert "keep going" in html
    assert "existing_workflow" in html
    assert render_to_string("partials/run_chain.html", {"run_chain": []}).strip() == ""


def test_continue_form_only_for_finished_runs():
    finished = render_to_string(
        "partials/run_continue.html", {"run": {"id": "r1", "completed_at": datetime.now(UTC)}}
    )
    unfinished = render_to_string(
        "partials/run_continue.html", {"run": {"id": "r1", "completed_at": None}}
    )
    assert 'hx-post="/runs/r1/continue/"' in finished
    assert 'value="queue"' in finished
    assert unfinished.strip() == ""


# --- API ---------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_api_continue_queues_and_returns_202(user_a):
    _create_run_sync("f134-api", user_a.id, success=False)
    process = MagicMock()
    process.id = "proc-api"
    process.properties = {"run_id": "new-run"}
    queue = AsyncMock(return_value=process)
    fake = MagicMock()
    fake.ensure_initialized = AsyncMock()
    fake.get_metrics.return_value = DjangoMetricsStore()
    client = APIClient()
    client.force_authenticate(user=user_a)

    with (
        patch("zebra_agent_web.api.views.agent_engine", fake),
        patch("zebra_agent_web.api.goals.queue_goal", queue),
    ):
        response = client.post(
            "/api/runs/f134-api/continue/", {"comment": "try again", "priority": 1}, format="json"
        )
        missing = client.post("/api/runs/nope/continue/", {"comment": "try again"}, format="json")
        invalid = client.post("/api/runs/f134-api/continue/", {}, format="json")

    assert response.status_code == 202
    assert response.json() == {
        "process_id": "proc-api",
        "run_id": "new-run",
        "continues_run_id": "f134-api",
        "status": "queued",
    }
    assert queue.call_args.args[0] == "goal of f134-api"
    assert queue.call_args.kwargs["continuation_comment"] == "try again"
    assert queue.call_args.kwargs["priority"] == 1
    assert missing.status_code == 404
    assert invalid.status_code == 400
