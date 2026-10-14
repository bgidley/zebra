"""Tests for the "Report a bug" button and Bug Report workflow (#186).

The view tests run the real ``bug_report.yaml`` on a ``DjangoStore`` so the
whole path is exercised: submit → process in the DB → /bugs/ → review task →
verdict shown on /bugs/.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState
from zebra.definitions.loader import load_definition_from_yaml
from zebra.storage.memory import InMemoryStore
from zebra.tasks.registry import ActionRegistry
from zebra_agent.library import SYSTEM_TAG, WorkflowLibrary, list_goal_workflows
from zebra_agent_web.api import bug_reports
from zebra_agent_web.storage import DjangoStore

WORKFLOW_PATH = (
    Path(__file__).parent.parent.parent.parent / "zebra-agent" / "workflows" / "bug_report.yaml"
)


@pytest.fixture
def definition():
    return load_definition_from_yaml(WORKFLOW_PATH.read_text())


def _client_context(**overrides) -> str:
    context = {
        "url": "http://testserver/dreams/",
        "title": "Dream Cycles - Zebra Agent",
        "user_agent": "TestBrowser/1.0",
        "viewport": {"width": 1280, "height": 800},
        "errors": [{"kind": "error", "message": "TypeError: x is undefined"}],
        "failed_requests": [{"kind": "response", "path": "/nav/needs-you/", "status": 500}],
    }
    context.update(overrides)
    return json.dumps(context)


# ---------------------------------------------------------------------------
# Workflow definition
# ---------------------------------------------------------------------------


async def test_goal_selector_never_offers_the_workflow(tmp_path):
    import shutil

    shutil.copy(WORKFLOW_PATH, tmp_path / WORKFLOW_PATH.name)
    library = WorkflowLibrary(tmp_path)

    [info] = await library.list_workflows()
    assert info.name == bug_reports.BUG_REPORT_WORKFLOW
    assert SYSTEM_TAG in info.tags
    assert await list_goal_workflows(library) == []


def test_workflow_has_one_review_task(definition):
    assert definition.name == bug_reports.BUG_REPORT_WORKFLOW
    assert list(definition.tasks) == [bug_reports.REVIEW_TASK]
    review = definition.tasks[bug_reports.REVIEW_TASK]
    assert review.auto is False
    schema = review.properties["schema"]
    assert schema["required"] == ["verdict"]
    assert set(schema["properties"]["verdict"]["enum"]) == set(bug_reports.VERDICTS)


async def test_review_completes_the_process(definition):
    from zebra.core.models import TaskResult

    store = InMemoryStore()
    registry = ActionRegistry()
    registry.register_defaults()
    wf_engine = WorkflowEngine(store, registry)
    process = await wf_engine.create_process(definition, properties={"bug_title": "x"})
    await wf_engine.start_process(process.id)

    [task] = await wf_engine.get_pending_tasks(process.id)
    await wf_engine.complete_task(task.id, TaskResult.ok(output={"verdict": "confirmed"}))

    process = await store.load_process(process.id)
    assert process.state == ProcessState.COMPLETE
    assert process.properties["__task_output_review"] == {"verdict": "confirmed"}


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_parse_user_report_trims_caps_and_defaults_severity():
    report = bug_reports.parse_user_report(
        {"title": "  Broken  ", "description": "d" * 20_000, "severity": "nonsense"}
    )
    assert report["title"] == "Broken"
    assert len(report["description"]) == bug_reports.TEXT_MAX
    assert report["severity"] == bug_reports.DEFAULT_SEVERITY
    assert report["expected"] == "" and report["steps"] == ""


@pytest.mark.parametrize("data", [{"description": "x"}, {"title": "x", "description": "  "}])
def test_parse_user_report_requires_title_and_description(data):
    with pytest.raises(bug_reports.BugReportError):
        bug_reports.parse_user_report(data)


@pytest.mark.parametrize(
    ("raw", "note"),
    [
        (None, "No client context"),
        ("not json", "not valid JSON"),
        ("[1, 2]", "not a JSON object"),
        (json.dumps({"x": "y" * 70_000}), "over"),
    ],
)
def test_bad_client_context_becomes_a_note(raw, note):
    assert note in bug_reports.parse_client_context(raw)["note"]


def test_client_context_object_is_kept():
    assert bug_reports.parse_client_context('{"url": "/x"}') == {"url": "/x"}


def test_resolve_page_names_the_view_and_its_arguments():
    route = bug_reports.resolve_page("https://zebra.example/tasks/abc123/?x=1")
    assert route == {
        "path": "/tasks/abc123/",
        "view": "human_task_form",
        "kwargs": {"task_id": "abc123"},
    }
    assert bug_reports.resolve_page("/no/such/page/")["view"] is None
    assert bug_reports.resolve_page(None) is None


# ---------------------------------------------------------------------------
# Linked state
# ---------------------------------------------------------------------------


async def test_linked_state_for_a_task_page_includes_its_process(definition):
    store = InMemoryStore()
    registry = ActionRegistry()
    registry.register_defaults()
    wf_engine = WorkflowEngine(store, registry)
    process = await wf_engine.create_process(definition, properties={"__error__": "boom"})
    await wf_engine.start_process(process.id)
    [task] = await wf_engine.get_pending_tasks(process.id)

    route = {"kwargs": {"task_id": task.id}}
    linked = await bug_reports.linked_state(route, store, metrics=None)

    assert linked["process_id"] == process.id
    assert linked["workflow_name"] == "Bug Report"
    assert linked["process_state"] == "running"
    assert linked["error"] == "boom"
    assert linked["task_definition_id"] == "review"


async def test_linked_state_for_a_run_page_uses_metrics():
    run = SimpleNamespace(
        id="run-1",
        workflow_name="Answer Question",
        success=False,
        error="timeout",
        started_at=datetime(2026, 10, 14, tzinfo=UTC),
        completed_at=None,
    )

    class _Metrics:
        async def get_run(self, run_id):
            return run if run_id == "run-1" else None

    linked = await bug_reports.linked_state(
        {"kwargs": {"run_id": "run-1"}}, InMemoryStore(), _Metrics()
    )
    assert linked["workflow_name"] == "Answer Question"
    assert linked["error"] == "timeout"


async def test_linked_state_failure_is_a_note_not_an_error():
    class _BrokenStore:
        async def load_process(self, process_id):
            raise RuntimeError("db down")

    linked = await bug_reports.linked_state(
        {"kwargs": {"process_id": "p1"}}, _BrokenStore(), metrics=None
    )
    assert "db down" in linked["note"]


# ---------------------------------------------------------------------------
# Markdown summary
# ---------------------------------------------------------------------------


def test_markdown_has_both_views():
    report = bug_reports.parse_user_report(
        {
            "title": "Diagram blank",
            "description": "The diagram is empty",
            "expected": "Tasks drawn",
            "steps": "1. Open a run",
            "severity": "major",
        }
    )
    technical = {
        "client": json.loads(_client_context()),
        "server": {
            "received_at": "2026-10-14T10:00:00+00:00",
            "version": {"short_hash": "abc1234", "date": "2026-10-14"},
            "route": {"path": "/dreams/", "view": "dream_cycles", "kwargs": {}},
        },
        "linked": {"process_id": "p1", "process_state": "failed"},
    }
    md = bug_reports.render_markdown(report, technical)

    for expected in (
        "### Diagram blank",
        "Gets in the way",
        "The diagram is empty",
        "#### Expected",
        "#### Steps to reproduce",
        "http://testserver/dreams/",
        "dream_cycles",
        "abc1234",
        "TestBrowser/1.0",
        "1280×800",
        "#### Linked state",
        "TypeError: x is undefined",
        "#### Failed requests (1)",
    ):
        assert expected in md


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


class _StubLibrary:
    def __init__(self, definition):
        self._definition = definition

    def get_workflow(self, name):
        if name != bug_reports.BUG_REPORT_WORKFLOW:
            raise ValueError(f"Unknown workflow: {name}")
        return self._definition


class _NoRunsMetrics:
    async def get_run(self, run_id):
        return None


@pytest.fixture
def django_engine(definition):
    """Point the web singletons at a DjangoStore-backed engine with the real YAML."""
    import zebra_agent_web.api.agent_engine as agent_engine_module
    import zebra_agent_web.api.engine as engine_module

    store = DjangoStore()
    registry = ActionRegistry()
    registry.register_defaults()
    wf_engine = WorkflowEngine(store, registry)

    saved = (
        engine_module._store,
        engine_module._engine,
        agent_engine_module._library,
        agent_engine_module._metrics,
    )
    engine_module._store = store
    engine_module._engine = wf_engine
    agent_engine_module._library = _StubLibrary(definition)
    agent_engine_module._metrics = _NoRunsMetrics()
    yield wf_engine
    (
        engine_module._store,
        engine_module._engine,
        agent_engine_module._library,
        agent_engine_module._metrics,
    ) = saved


@pytest.fixture(autouse=True)
def _setup_complete(db):
    from zebra_agent_web.api.identity import set_identity_sync

    set_identity_sync("Test User")


def _report_form(**overrides) -> dict:
    form = {
        "title": "Dream page crashed",
        "description": "Got a 500 after clicking a cycle",
        "expected": "The cycle details",
        "steps": "1. Open /dreams/",
        "severity": "blocker",
        "client_context": _client_context(),
    }
    form.update(overrides)
    return form


def _bug_processes():
    from zebra_agent_web.api.models import ProcessInstanceModel

    return list(ProcessInstanceModel.objects.all())


@pytest.mark.django_db(transaction=True)
def test_report_button_and_dialog_are_on_every_page(authenticated_client):
    response = authenticated_client.get("/bugs/")
    html = response.content.decode()
    assert response.status_code == 200
    assert 'data-testid="report-bug-button"' in html
    assert 'data-testid="bug-report-dialog"' in html
    assert 'hx-post="/bugs/report/"' in html
    assert "js/bug-report.js" in html
    assert 'data-testid="bug-report-empty"' in html


@pytest.mark.django_db(transaction=True)
def test_submit_records_a_bug_report_process(authenticated_client, test_user, django_engine):
    response = authenticated_client.post("/bugs/report/", _report_form())

    assert response.status_code == 200
    assert 'data-testid="bug-report-sent"' in response.content.decode()

    [model] = _bug_processes()
    assert model.state == "running"
    props = json.loads(model.properties)
    assert props["goal"] == "Bug report: Dream page crashed"
    assert props["bug_report"]["severity"] == "blocker"
    assert props["__user_id__"] == test_user.id
    technical = props["technical_context"]
    assert technical["client"]["errors"][0]["message"] == "TypeError: x is undefined"
    assert technical["server"]["user"]["username"] == "testuser"
    assert technical["server"]["route"]["view"] == "dream_cycles"
    assert "short_hash" in technical["server"]["version"]
    assert "Got a 500" in props["bug_report_markdown"]


@pytest.mark.django_db(transaction=True)
def test_unreviewed_report_counts_in_the_needs_you_badge(authenticated_client, django_engine):
    authenticated_client.post("/bugs/report/", _report_form())
    html = authenticated_client.get("/nav/needs-you/").content.decode()
    assert 'aria-label="1 waiting on you"' in html


@pytest.mark.django_db(transaction=True)
def test_submit_from_a_task_page_links_that_process(authenticated_client, django_engine):
    authenticated_client.post("/bugs/report/", _report_form(title="first"))
    [first] = _bug_processes()
    from zebra_agent_web.api.models import TaskInstanceModel

    task_id = TaskInstanceModel.objects.get(process_id=first.id).id

    authenticated_client.post(
        "/bugs/report/",
        _report_form(title="second", client_context=_client_context(url=f"/tasks/{task_id}/")),
    )
    second = next(p for p in _bug_processes() if p.id != first.id)
    linked = json.loads(second.properties)["technical_context"]["linked"]
    assert linked["process_id"] == first.id
    assert linked["task_id"] == task_id


@pytest.mark.django_db(transaction=True)
def test_submit_survives_bad_client_context(authenticated_client, django_engine):
    response = authenticated_client.post("/bugs/report/", _report_form(client_context="{oops"))
    assert response.status_code == 200
    [model] = _bug_processes()
    client = json.loads(model.properties)["technical_context"]["client"]
    assert "not valid JSON" in client["note"]


@pytest.mark.django_db(transaction=True)
def test_submit_without_description_is_rejected(authenticated_client, django_engine):
    response = authenticated_client.post("/bugs/report/", _report_form(description=""))
    assert response.status_code == 400
    assert 'data-testid="bug-report-error"' in response.content.decode()
    assert _bug_processes() == []


@pytest.mark.django_db(transaction=True)
def test_submit_requires_sign_in(client, django_engine):
    response = client.post("/bugs/report/", _report_form())
    assert response.status_code in (302, 403)
    assert _bug_processes() == []


@pytest.mark.django_db(transaction=True)
def test_bugs_page_lists_report_then_shows_review_verdict(authenticated_client, django_engine):
    authenticated_client.post("/bugs/report/", _report_form())
    [model] = _bug_processes()
    from zebra_agent_web.api.models import TaskInstanceModel

    task_id = TaskInstanceModel.objects.get(process_id=model.id).id

    html = authenticated_client.get("/bugs/").content.decode()
    assert "Dream page crashed" in html
    assert "Awaiting review" in html
    assert f"/tasks/{task_id}/" in html
    assert "1 waiting for review" in html

    # The review task renders the markdown report and accepts a verdict
    form_html = authenticated_client.get(f"/tasks/{task_id}/").content.decode()
    assert "Got a 500 after clicking a cycle" in form_html
    response = authenticated_client.post(
        f"/tasks/{task_id}/submit/",
        {
            "verdict": "needs_info",
            "priority": "high",
            "issue_url": "https://gitlab.com/gidley/zebra/-/issues/1",
            "notes": "Which cycle?",
        },
    )
    assert response.status_code == 200

    model.refresh_from_db()
    assert model.state == "complete"
    html = authenticated_client.get("/bugs/").content.decode()
    assert "Needs more info" in html
    assert "Which cycle?" in html
    assert "https://gitlab.com/gidley/zebra/-/issues/1" in html
    assert "Awaiting review" not in html


def test_summary_drops_non_http_issue_links():
    model = SimpleNamespace(
        id="p1",
        state="complete",
        created_at=datetime(2026, 10, 14, tzinfo=UTC),
        properties=json.dumps(
            {
                "bug_report": {"title": "t", "description": "d", "severity": "minor"},
                "__task_output_review": {
                    "verdict": "confirmed",
                    "issue_url": "javascript:alert(1)",
                },
            }
        ),
    )
    summary = bug_reports.summarize_report(model)
    assert summary["issue_url"] is None
    assert summary["verdict_label"] == "Confirmed"
    assert summary["severity_label"] == "Minor annoyance"
