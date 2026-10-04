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
async def test_get_run_keeps_unowned_runs_visible(user_a):
    """API-submitted and legacy runs have no owner; their pages must not 404."""

    @sync_to_async
    def _create():
        WorkflowRunModel.objects.create(
            id="f116-unowned",
            workflow_name="wf",
            goal="g",
            started_at=datetime.now(UTC),
            user_id=None,
        )

    await _create()

    with _AsUser(user_a):
        assert (await DjangoMetricsStore().get_run("f116-unowned")).id == "f116-unowned"


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


@pytest.mark.django_db(transaction=True)
async def test_record_run_persists_continuation_fields_and_chain(user_a):
    store = DjangoMetricsStore()
    now = datetime.now(UTC)
    root = WorkflowRun(id="f134-root", workflow_name="Research", goal="g", started_at=now)
    cont = WorkflowRun(
        id="f134-cont",
        workflow_name="Research",
        goal="g",
        started_at=now,
        extends_run_id="f134-root",
        continuation_comment="Stopped after step 2",
        continuation_decision="new_workflow",
        continuation_rationale="No library workflow covers the rest",
    )

    with _AsUser(user_a):
        await store.record_run(root)
        await store.record_run(cont)
        loaded = await store.get_run("f134-cont")
        chain = await store.get_run_chain("f134-cont")
        continuations = await store.get_continuations_since(now - timedelta(minutes=1))

    assert loaded.continuation_comment == "Stopped after step 2"
    assert loaded.continuation_decision == "new_workflow"
    assert loaded.continuation_rationale == "No library workflow covers the rest"
    assert [r.id for r in chain] == ["f134-root", "f134-cont"]
    assert [r.id for r in continuations] == ["f134-cont"]


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


@pytest.mark.django_db(transaction=True)
async def test_run_goal_form_has_no_workflow_list(user_a, fake_agent_engine):
    """F125: the Run Goal page no longer lists the workflow library."""
    request = RequestFactory().get("/run/")
    request.user = user_a

    with _AsUser(user_a):
        response = await web_views.run_goal_form(request)

    assert response.status_code == 200
    assert b"Available Workflows" not in response.content
    fake_agent_engine.get_library.return_value.list_workflows.assert_not_called()
