"""Per-workflow continuation rate in the stores, API and web UI (#137)."""

from datetime import UTC, datetime

import pytest
from django.template.loader import render_to_string
from zebra_agent.metrics import WorkflowRun, WorkflowStats
from zebra_agent_web.api import web_views
from zebra_agent_web.metrics_store import DjangoMetricsStore

pytestmark = [pytest.mark.django_db(transaction=True)]


def _run(run_id: str, workflow: str, extends: str | None = None) -> WorkflowRun:
    now = datetime.now(UTC)
    return WorkflowRun(
        id=run_id,
        workflow_name=workflow,
        goal="g",
        started_at=now,
        completed_at=now,
        success=True,
        extends_run_id=extends,
    )


@pytest.fixture
def rf_user(db):
    from django.contrib.auth import get_user_model
    from django.test import RequestFactory
    from zebra_agent_web.api.identity import set_identity_sync

    set_identity_sync("Test User")
    user = get_user_model().objects.create_user(username="rate-user")

    def _make(path):
        request = RequestFactory().get(path)
        request.user = user
        return request

    return _make


async def test_django_store_counts_continued_runs():
    store = DjangoMetricsStore()
    for run in (
        _run("r1", "Research"),
        _run("r2", "Research"),
        _run("r3", "Research", extends="r1"),
        _run("r4", "Summarise", extends="r1"),
    ):
        await store.record_run(run)

    stats = await store.get_stats("Research")
    assert (stats.total_runs, stats.continued_runs) == (3, 1)
    assert stats.continuation_rate == pytest.approx(1 / 3)

    by_name = {s.workflow_name: s for s in await store.get_all_stats()}
    assert by_name["Research"].continued_runs == 1
    assert by_name["Summarise"].continued_runs == 0


def test_continuation_rates_only_lists_continued_workflows():
    rates = web_views._continuation_rates(
        [
            WorkflowStats(workflow_name="Research", total_runs=4, continued_runs=1),
            WorkflowStats(workflow_name="Writer", total_runs=3, continued_runs=0),
        ]
    )
    assert rates == {"Research": "25%"}


def test_library_list_shows_continuation_rate_only_when_set():
    workflows = [
        {
            "name": "Research",
            "description": "",
            "tags": [],
            "use_count": 4,
            "success_rate": "75%",
            "continuation_rate": "25%",
        },
        {
            "name": "Writer",
            "description": "",
            "tags": [],
            "use_count": 3,
            "success_rate": "100%",
            "continuation_rate": None,
        },
    ]
    html = render_to_string("partials/workflow_library_list.html", {"workflows": workflows})
    assert "25% continued" in html
    assert html.count("continued</span>") == 1


def test_workflow_stats_serializer_includes_continuation():
    from zebra_agent_web.api.serializers import WorkflowStatsSerializer

    data = WorkflowStatsSerializer(
        {
            "total_runs": 4,
            "successful_runs": 3,
            "success_rate": 0.75,
            "continued_runs": 1,
            "continuation_rate": 0.25,
            "avg_rating": None,
            "last_used": None,
        }
    ).data
    assert data["continued_runs"] == 1
    assert data["continuation_rate"] == 0.25


async def test_workflow_detail_shows_continued_card(monkeypatch, rf_user):
    import zebra_agent_web.api.agent_engine as agent_engine_module

    class _Info:
        name = "Research"
        description = ""
        tags: list[str] = []

    class _Library:
        def get_workflow_yaml(self, name):
            return "name: Research\n"

        async def list_workflows(self):
            return [_Info()]

    class _Metrics:
        async def get_stats(self, name):
            return WorkflowStats(
                workflow_name=name, total_runs=4, successful_runs=3, continued_runs=1
            )

    async def _noop():
        return None

    monkeypatch.setattr(agent_engine_module, "ensure_initialized", _noop)
    monkeypatch.setattr(agent_engine_module, "get_library", lambda: _Library())
    monkeypatch.setattr(agent_engine_module, "get_metrics", lambda: _Metrics())

    response = await web_views.workflow_detail(rf_user("/workflows/Research/"), "Research")
    html = response.content.decode()
    assert response.status_code == 200
    assert "Continued" in html
    assert "25%" in html
    assert "1 of 4 runs" in html
