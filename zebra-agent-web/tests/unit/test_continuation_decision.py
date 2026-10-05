"""Run detail shows the continuation decision and rationale (F135)."""

from datetime import UTC, datetime

import pytest
from django.template.loader import render_to_string
from zebra.core.engine import WorkflowEngine
from zebra.storage.memory import InMemoryStore
from zebra.tasks.registry import ActionRegistry
from zebra_agent.metrics import WorkflowRun

pytestmark = [pytest.mark.django_db(transaction=True)]


def _run(**extra) -> WorkflowRun:
    return WorkflowRun(
        id="run-2",
        workflow_name="Writer",
        goal="Polish the draft",
        started_at=datetime(2026, 10, 4, tzinfo=UTC),
        completed_at=datetime(2026, 10, 4, tzinfo=UTC),
        success=True,
        extends_run_id="run-1",
        **extra,
    )


class _StubMetricsStore:
    def __init__(self, run):
        self._run = run

    async def get_run(self, run_id):
        return self._run if run_id == self._run.id else None

    async def get_task_executions(self, run_id):
        return []


class _StubLibrary:
    def get_workflow(self, name):
        raise ValueError(name)


@pytest.fixture(autouse=True)
def _setup_complete(db):
    from zebra_agent_web.api.identity import set_identity_sync

    set_identity_sync("Test User")


@pytest.fixture
def patch_engine(monkeypatch):
    import zebra_agent_web.api.agent_engine as agent_engine_module
    import zebra_agent_web.api.engine as engine_module

    def _patch(run):
        store = InMemoryStore()
        monkeypatch.setattr(engine_module, "_store", store)
        monkeypatch.setattr(engine_module, "_engine", WorkflowEngine(store, ActionRegistry()))
        monkeypatch.setattr(agent_engine_module, "_metrics", _StubMetricsStore(run))
        monkeypatch.setattr(agent_engine_module, "_library", _StubLibrary())

    return _patch


@pytest.fixture
def client(db):
    from django.contrib.auth import get_user_model
    from django.test import AsyncClient

    user = get_user_model().objects.create_user(username="testuser")
    c = AsyncClient()
    c.force_login(user)
    return c


def test_partial_renders_decision_and_rationale():
    html = render_to_string(
        "partials/_continuation_decision.html",
        {
            "run": {
                "continuation_decision": "new_workflow",
                "continuation_rationale": "No library workflow publishes posts.",
            }
        },
    )
    assert "Continuation Decision" in html
    assert "New workflow" in html
    assert "No library workflow publishes posts." in html


def test_partial_renders_nothing_without_decision():
    html = render_to_string("partials/_continuation_decision.html", {"run": {"goal": "x"}})
    assert html.strip() == ""


async def test_run_detail_shows_continuation_decision(client, patch_engine):
    patch_engine(
        _run(
            continuation_decision="same_workflow",
            continuation_rationale="The ranking step only needs another pass.",
        )
    )

    response = await client.get("/runs/run-2/")

    html = response.content.decode()
    assert response.status_code == 200
    assert 'data-testid="continuation-decision"' in html
    assert "Same workflow" in html
    assert "The ranking step only needs another pass." in html


async def test_run_detail_without_continuation_has_no_panel(client, patch_engine):
    patch_engine(_run())

    response = await client.get("/runs/run-2/")

    assert response.status_code == 200
    assert 'data-testid="continuation-decision"' not in response.content.decode()
