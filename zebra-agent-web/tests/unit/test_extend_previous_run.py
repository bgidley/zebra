"""Tests for extending a previous run (F116): ownership, lookup, and lineage."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from zebra_agent.metrics import WorkflowRun
from zebra_agent_web.api import web_views
from zebra_agent_web.api.models import WorkflowRunModel
from zebra_agent_web.metrics_store import DjangoMetricsStore
from zebra_agent_web.middleware import _current_user_id_var

User = get_user_model()


@pytest.fixture
def user_a(db):
    return User.objects.create_user(username="f116_user_a", password="x")


@pytest.fixture
def user_b(db):
    return User.objects.create_user(username="f116_user_b", password="x")


@sync_to_async
def _create_run(run_id: str, user_id: int, *, completed: bool = True, age_days: int = 0):
    ts = datetime.now(UTC) - timedelta(days=age_days)
    WorkflowRunModel.objects.create(
        id=run_id,
        workflow_name="Summariser",
        goal=f"goal of {run_id}",
        output=f"output of {run_id}",
        started_at=ts,
        completed_at=ts if completed else None,
        success=True,
        user_id=user_id,
    )


@pytest.fixture
def fake_agent_engine():
    """Point web_views at a real DjangoMetricsStore without initialising the agent."""
    fake = MagicMock()
    fake.ensure_initialized = AsyncMock()
    fake.get_metrics.return_value = DjangoMetricsStore()
    library = MagicMock()
    library.list_workflows = AsyncMock(return_value=[])
    fake.get_library.return_value = library
    with patch.object(web_views, "agent_engine", fake):
        yield fake


class _AsUser:
    """Set the current-user contextvar as CurrentUserMiddleware would."""

    def __init__(self, user):
        self.user = user

    def __enter__(self):
        self.token = _current_user_id_var.set(self.user.id)

    def __exit__(self, *exc):
        _current_user_id_var.reset(self.token)


# --- store -------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
async def test_get_run_is_scoped_to_current_user(user_a, user_b):
    await _create_run("f116-b-run", user_b.id)
    store = DjangoMetricsStore()

    with _AsUser(user_a):
        assert await store.get_run("f116-b-run") is None
    with _AsUser(user_b):
        assert (await store.get_run("f116-b-run")).id == "f116-b-run"
    # Daemon / system paths (no user) stay unfiltered
    assert (await store.get_run("f116-b-run")).id == "f116-b-run"


@pytest.mark.django_db(transaction=True)
async def test_record_run_persists_extends_run_id(user_a):
    store = DjangoMetricsStore()
    run = WorkflowRun(
        id="f116-followup",
        workflow_name="Summariser",
        goal="shorter please",
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        extends_run_id="f116-original",
    )

    with _AsUser(user_a):
        await store.record_run(run)
        loaded = await store.get_run("f116-followup")

    assert loaded.extends_run_id == "f116-original"


# --- views -------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
async def test_previous_run_context_ignores_other_users_runs(user_a, user_b, fake_agent_engine):
    await _create_run("f116-mine", user_a.id)
    await _create_run("f116-theirs", user_b.id)

    with _AsUser(user_a):
        mine = await web_views._previous_run_context("f116-mine")
        theirs = await web_views._previous_run_context("f116-theirs")

    assert mine["run_id"] == "f116-mine"
    assert mine["output"] == "output of f116-mine"
    assert theirs is None


@pytest.mark.django_db(transaction=True)
async def test_previous_run_context_ignores_incomplete_runs(user_a, fake_agent_engine):
    await _create_run("f116-running", user_a.id, completed=False)

    with _AsUser(user_a):
        assert await web_views._previous_run_context("f116-running") is None


@pytest.mark.django_db(transaction=True)
async def test_run_context_partial_404_for_other_users_run(user_a, user_b, fake_agent_engine):
    await _create_run("f116-private", user_b.id)
    request = RequestFactory().get("/runs/f116-private/context/")
    request.user = user_a

    with _AsUser(user_a):
        response = await web_views.run_context_partial(request, "f116-private")

    assert response.status_code == 404


@pytest.mark.django_db(transaction=True)
async def test_extend_link_preselects_run_older_than_recent_list(user_a, fake_agent_engine):
    await _create_run("f116-old", user_a.id, age_days=30)
    for i in range(12):
        await _create_run(f"f116-new-{i}", user_a.id)
    request = RequestFactory().get("/run/?extend_from=f116-old")
    request.user = user_a

    with (
        _AsUser(user_a),
        patch.object(web_views, "render", return_value=MagicMock()) as render,
    ):
        await web_views.run_goal_form(request)

    context = render.call_args.args[2]
    assert context["extend_from_run"].id == "f116-old"
    assert context["recent_runs"][0].id == "f116-old"
