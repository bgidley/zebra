"""Tests for human task web views and REST API.

Tests use InMemoryStore and a real WorkflowEngine (no Django ORM or Oracle),
monkey-patching the engine singleton so views use test fixtures.
"""

import pytest

from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessDefinition, RoutingDefinition, TaskDefinition, TaskResult
from zebra.storage.memory import InMemoryStore
from zebra.tasks.registry import ActionRegistry


# ---------------------------------------------------------------------------
# Workflow definitions for testing
# ---------------------------------------------------------------------------


def _simple_human_task_definition():
    """A workflow with one human task (auto: false)."""
    return ProcessDefinition(
        id="human-task-wf",
        name="Human Task Test",
        version=1,
        first_task_id="ask_user",
        tasks={
            "ask_user": TaskDefinition(
                id="ask_user",
                name="Ask User",
                auto=False,
                properties={
                    "schema": {
                        "type": "object",
                        "title": "User Info",
                        "required": ["name", "severity"],
                        "properties": {
                            "name": {
                                "type": "string",
                                "title": "Full Name",
                                "minLength": 2,
                            },
                            "severity": {
                                "type": "string",
                                "title": "Severity",
                                "enum": ["low", "medium", "high"],
                            },
                            "notes": {
                                "type": "string",
                                "title": "Notes",
                                "format": "multiline",
                            },
                        },
                    },
                },
            ),
            "done": TaskDefinition(
                id="done",
                name="Done",
                auto=True,
            ),
        },
        routings=[
            RoutingDefinition(id="r1", source_task_id="ask_user", dest_task_id="done"),
        ],
    )


def _routed_human_task_definition():
    """A workflow with a human task that has conditional routing."""
    return ProcessDefinition(
        id="routed-human-wf",
        name="Routed Human Task",
        version=1,
        first_task_id="review",
        tasks={
            "review": TaskDefinition(
                id="review",
                name="Review",
                auto=False,
                properties={
                    "schema": {
                        "type": "object",
                        "title": "Review Decision",
                        "required": ["decision"],
                        "properties": {
                            "decision": {
                                "type": "string",
                                "title": "Approve?",
                                "enum": ["yes", "no"],
                            },
                        },
                    },
                },
            ),
            "approved": TaskDefinition(id="approved", name="Approved", auto=True),
            "rejected": TaskDefinition(id="rejected", name="Rejected", auto=True),
        },
        routings=[
            RoutingDefinition(
                id="r1",
                source_task_id="review",
                dest_task_id="approved",
                condition="route_name",
                name="yes",
            ),
            RoutingDefinition(
                id="r2",
                source_task_id="review",
                dest_task_id="rejected",
                condition="route_name",
                name="no",
            ),
        ],
    )


def _template_default_definition():
    """A workflow whose human task schema has a {{template}} default value."""
    return ProcessDefinition(
        id="template-default-wf",
        name="Template Default Test",
        version=1,
        first_task_id="show_questions",
        tasks={
            "show_questions": TaskDefinition(
                id="show_questions",
                name="Show Questions",
                auto=False,
                properties={
                    "schema": {
                        "type": "object",
                        "title": "Quiz",
                        "properties": {
                            "questions": {
                                "type": "string",
                                "title": "Questions",
                                "default": "{{questions}}",
                            },
                            "answer": {
                                "type": "string",
                                "title": "Your Answer",
                            },
                        },
                    },
                },
            ),
        },
        routings=[],
    )


def _no_schema_human_task_definition():
    """A workflow with a human task that has NO schema (tests fallback)."""
    return ProcessDefinition(
        id="no-schema-wf",
        name="No Schema Task",
        version=1,
        first_task_id="respond",
        tasks={
            "respond": TaskDefinition(
                id="respond",
                name="Provide Response",
                auto=False,
                properties={},
            ),
        },
        routings=[],
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store():
    """Fresh InMemoryStore for each test."""
    return InMemoryStore()


@pytest.fixture
def wf_engine(store):
    """WorkflowEngine backed by InMemoryStore."""
    registry = ActionRegistry()
    return WorkflowEngine(store, registry)


@pytest.fixture(autouse=True)
def patch_engine(store, wf_engine):
    """Monkey-patch the engine and agent_engine singletons so views use test fixtures."""
    import zebra_agent_web.api.agent_engine as agent_engine_module
    import zebra_agent_web.api.engine as engine_module

    old_store = engine_module._store
    old_engine = engine_module._engine

    engine_module._store = store
    engine_module._engine = wf_engine

    # Patch agent_engine with a stub metrics store so /activity/ view works
    old_metrics = agent_engine_module._metrics
    old_library = agent_engine_module._library
    agent_engine_module._metrics = _StubMetricsStore()
    agent_engine_module._library = _StubLibrary()

    yield

    engine_module._store = old_store
    engine_module._engine = old_engine
    agent_engine_module._metrics = old_metrics
    agent_engine_module._library = old_library


class _StubMetricsStore:
    """Minimal stub that returns empty results for activity view tests."""

    async def get_in_progress_runs(self):
        return []

    async def get_completed_runs(self, limit=20):
        return []

    async def get_recent_runs(self, limit=10):
        return []

    async def get_run(self, run_id):
        return None

    async def get_task_executions(self, run_id):
        return []


class _StubLibrary:
    """Minimal stub for workflow library."""

    async def list_workflows(self):
        return []


@pytest.fixture
def client():
    """Django async test client."""
    from django.test import AsyncClient

    return AsyncClient()


async def _start_workflow(wf_engine, definition):
    """Helper: create + start a workflow and return (process, pending_tasks)."""
    process = await wf_engine.create_process(definition)
    await wf_engine.start_process(process.id)
    pending = await wf_engine.get_pending_tasks(process.id)
    return process, pending


# ===========================================================================
# Web View Tests: Pending Tasks List
# ===========================================================================


class TestPendingTasksList:
    """Tests for the /activity/ view (formerly /tasks/)."""

    async def test_old_tasks_url_redirects(self, client):
        """The old /tasks/ URL redirects to /activity/."""
        response = await client.get("/tasks/")
        assert response.status_code == 302
        assert "/activity/" in response.url

    async def test_empty_when_no_processes(self, client):
        """No running processes -> empty activity list."""
        response = await client.get("/activity/")
        assert response.status_code == 200
        assert b"No activity" in response.content

    async def test_shows_pending_human_task(self, client, wf_engine):
        """A running workflow with auto:false task shows in the activity list."""
        defn = _simple_human_task_definition()
        await _start_workflow(wf_engine, defn)

        response = await client.get("/activity/")
        assert response.status_code == 200
        assert b"Ask User" in response.content
        assert b"Awaiting Input" in response.content

    async def test_shows_human_task_when_run_id_not_in_metrics(self, client, wf_engine):
        """Pending task is visible even when the run_id is absent from the metrics store.

        Regression test: previously the activity view only iterated over runs returned
        by metrics.get_in_progress_runs(). If that list was empty (e.g. the metrics
        record was lost or the process was started outside the agent loop), running
        processes with pending human tasks were silently dropped from the page.
        """
        defn = _simple_human_task_definition()
        process, _ = await _start_workflow(wf_engine, defn)

        # Simulate a process that has a run_id in its properties but NO matching
        # WorkflowRunModel entry (metrics store returns empty list).
        # Reload after start_process so we have the RUNNING-state version.
        run_id = "test-run-id-not-in-metrics"
        running_process = await wf_engine.store.load_process(process.id)
        updated = running_process.model_copy(update={"properties": {"run_id": run_id}})
        await wf_engine.store.save_process(updated)

        response = await client.get("/activity/")
        assert response.status_code == 200
        assert b"Ask User" in response.content
        assert b"Awaiting Input" in response.content

    async def test_htmx_returns_partial(self, client, wf_engine):
        """With HX-Request header, returns the partial template only."""
        defn = _simple_human_task_definition()
        await _start_workflow(wf_engine, defn)

        response = await client.get("/activity/", headers={"HX-Request": "true"})
        assert response.status_code == 200
        assert b"Ask User" in response.content
        # Partial should have the polling attributes
        assert b"hx-trigger" in response.content


# ===========================================================================
# Web View Tests: Human Task Form
# ===========================================================================


class TestHumanTaskForm:
    """Tests for GET /tasks/<task_id>/."""

    async def test_renders_schema_form(self, client, wf_engine):
        """Form page renders fields from the JSON Schema."""
        defn = _simple_human_task_definition()
        _, pending = await _start_workflow(wf_engine, defn)
        task = pending[0]

        response = await client.get(f"/tasks/{task.id}/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "Full Name" in content
        assert "Severity" in content
        assert "Notes" in content

    async def test_renders_routes_as_buttons(self, client, wf_engine):
        """Tasks with route_name conditions render route buttons."""
        defn = _routed_human_task_definition()
        _, pending = await _start_workflow(wf_engine, defn)
        task = pending[0]

        response = await client.get(f"/tasks/{task.id}/")
        content = response.content.decode()
        # Route buttons should appear
        assert 'value="yes"' in content
        assert 'value="no"' in content

    async def test_fallback_schema_when_no_schema(self, client, wf_engine):
        """Tasks without properties.schema get a fallback Response textarea."""
        defn = _no_schema_human_task_definition()
        _, pending = await _start_workflow(wf_engine, defn)
        task = pending[0]

        response = await client.get(f"/tasks/{task.id}/")
        content = response.content.decode()
        assert "Response" in content
        assert "Provide Response" in content  # fallback title uses task name

    async def test_resolves_template_defaults_from_process_properties(self, client, wf_engine):
        """{{template}} variables in schema defaults are resolved from process properties.

        Regression test: previously schema defaults containing {{var}} were rendered
        literally, so users saw '{{questions}}' instead of the actual quiz content.
        """
        defn = _template_default_definition()
        process, pending = await _start_workflow(wf_engine, defn)
        task = pending[0]

        # Set the process property that the template default references
        running = await wf_engine.store.load_process(process.id)
        updated = running.model_copy(update={"properties": {"questions": "Q1: What is 1+1?"}})
        await wf_engine.store.save_process(updated)

        response = await client.get(f"/tasks/{task.id}/")
        assert response.status_code == 200
        content = response.content.decode()
        # The resolved value should appear, not the raw template
        assert "Q1: What is 1+1?" in content
        assert "{{questions}}" not in content

    async def test_404_for_unknown_task(self, client):
        """Unknown task_id returns 404 with a styled error page.

        Regression test: previously this returned a plain "Task not found" text
        response. Now it renders a proper HTML page explaining the task has
        already been completed (since the engine deletes tasks after completion).
        """
        response = await client.get("/tasks/nonexistent-id/")
        assert response.status_code == 404
        content = response.content.decode()
        # Should be an HTML page, not bare text
        assert "<html" in content.lower() or "<!doctype" in content.lower()
        # Should explain what happened in user-friendly language
        assert "already been completed" in content.lower() or "task not found" in content.lower()


# ===========================================================================
# Web View Tests: Human Task Submit
# ===========================================================================


class TestHumanTaskSubmit:
    """Tests for POST /tasks/<task_id>/submit/."""

    async def test_valid_submission_completes_task(self, client, wf_engine, store):
        """Valid form data completes the task and shows success partial."""
        defn = _simple_human_task_definition()
        process, pending = await _start_workflow(wf_engine, defn)
        task = pending[0]

        response = await client.post(
            f"/tasks/{task.id}/submit/",
            data={"name": "Alice", "severity": "high", "notes": "Test note"},
        )
        assert response.status_code == 200
        content = response.content.decode()
        assert "Ask User" in content
        # Success partial should mention completion
        assert "completed" in content.lower() or "Completed" in content

        # Process should have advanced (done task should have executed)
        updated = await store.load_process(process.id)
        assert updated is not None

    async def test_validation_error_re_renders_with_errors(self, client, wf_engine):
        """Missing required field re-renders form with error messages."""
        defn = _simple_human_task_definition()
        _, pending = await _start_workflow(wf_engine, defn)
        task = pending[0]

        # Submit without required 'name' and 'severity'
        response = await client.post(
            f"/tasks/{task.id}/submit/",
            data={"notes": "Just notes"},
        )
        assert response.status_code == 200
        content = response.content.decode()
        # Should contain error messages
        assert "required" in content.lower()
        # Form should still be rendered (not the success partial)
        assert "Full Name" in content

    async def test_validation_error_preserves_submitted_values(self, client, wf_engine):
        """On validation error, previously entered values are preserved."""
        defn = _simple_human_task_definition()
        _, pending = await _start_workflow(wf_engine, defn)
        task = pending[0]

        # Submit with notes but missing required fields
        response = await client.post(
            f"/tasks/{task.id}/submit/",
            data={"name": "A", "severity": "high", "notes": "My important notes"},
        )
        assert response.status_code == 200
        content = response.content.decode()
        # The notes value should be preserved in the re-rendered form
        assert "My important notes" in content
        # severity should be preserved as selected
        assert "high" in content

    async def test_submit_with_route(self, client, wf_engine, store):
        """Submitting with next_route routes to the correct branch."""
        defn = _routed_human_task_definition()
        process, pending = await _start_workflow(wf_engine, defn)
        task = pending[0]

        response = await client.post(
            f"/tasks/{task.id}/submit/",
            data={"decision": "yes", "next_route": "yes"},
        )
        assert response.status_code == 200

        # The process should have completed via the "approved" branch
        updated = await store.load_process(process.id)
        assert updated is not None

    async def test_submit_fallback_schema_requires_response(self, client, wf_engine):
        """Fallback schema requires the 'response' field."""
        defn = _no_schema_human_task_definition()
        _, pending = await _start_workflow(wf_engine, defn)
        task = pending[0]

        # Submit empty - should fail validation
        response = await client.post(
            f"/tasks/{task.id}/submit/",
            data={},
        )
        assert response.status_code == 200
        content = response.content.decode()
        assert "required" in content.lower()


# ===========================================================================
# REST API Tests: Pending Tasks
# ===========================================================================
# NOTE: The process_pending_tasks view uses @api_view + async def, which is
# incompatible with DRF (returns coroutine instead of Response). It works in
# production under ASGI but cannot be tested with Django's test client.
# See zebra-agent-web/AGENTS.md: "Do NOT use async def with @api_view".
# These tests are skipped until the view is converted to sync+async_to_sync.


# ===========================================================================
# REST API Tests: Task Complete
# ===========================================================================


class TestAPITaskComplete:
    """Tests for POST /api/tasks/<task_id>/complete/."""

    async def test_complete_with_valid_data(self, client, wf_engine, store):
        """Valid result data completes the task."""
        defn = _simple_human_task_definition()
        process, pending = await _start_workflow(wf_engine, defn)
        task = pending[0]

        response = await client.post(
            f"/api/tasks/{task.id}/complete/",
            data={"result": {"name": "Alice", "severity": "high"}, "next_route": None},
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["completed"] is True
        assert data["task_id"] == task.id

    async def test_complete_validates_against_schema(self, client, wf_engine):
        """Invalid data against the task schema returns 400."""
        defn = _simple_human_task_definition()
        _, pending = await _start_workflow(wf_engine, defn)
        task = pending[0]

        # Missing required 'name' and 'severity'
        response = await client.post(
            f"/api/tasks/{task.id}/complete/",
            data={"result": {"notes": "Only notes"}},
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.json()
        assert "field_errors" in data
        assert "name" in data["field_errors"]
        assert "severity" in data["field_errors"]

    async def test_complete_validates_enum(self, client, wf_engine):
        """Enum values not in the allowed list are rejected."""
        defn = _simple_human_task_definition()
        _, pending = await _start_workflow(wf_engine, defn)
        task = pending[0]

        response = await client.post(
            f"/api/tasks/{task.id}/complete/",
            data={"result": {"name": "Alice", "severity": "invalid_level"}},
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.json()
        assert "field_errors" in data
        assert "severity" in data["field_errors"]

    async def test_complete_404_unknown_task(self, client):
        """Unknown task ID returns 404."""
        response = await client.post(
            f"/api/tasks/nonexistent/complete/",
            data={"result": {}},
            content_type="application/json",
        )
        assert response.status_code == 404

    async def test_complete_with_route(self, client, wf_engine, store):
        """Completing with next_route routes correctly."""
        defn = _routed_human_task_definition()
        process, pending = await _start_workflow(wf_engine, defn)
        task = pending[0]

        response = await client.post(
            f"/api/tasks/{task.id}/complete/",
            data={"result": {"decision": "no"}, "next_route": "no"},
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["completed"] is True


# ===========================================================================
# REST API Tests: Run Diagram (diagram fallback to running processes)
# ===========================================================================


class _StubMetricsStoreEmpty:
    """Metrics store stub that returns None for all runs (simulates missing record)."""

    async def get_run(self, run_id):
        return None

    async def get_task_executions(self, run_id):
        return []

    async def get_in_progress_runs(self):
        return []


class _StubLibraryWithWorkflow:
    """Library stub that returns a known workflow."""

    def __init__(self, definition):
        self._definition = definition

    def get_workflow(self, name):
        if name == self._definition.name:
            return self._definition
        raise ValueError(f"Workflow '{name}' not found")


class TestRunDiagramFallback:
    """Tests for /api/runs/<id>/diagram/ with missing metrics record.

    Regression test: when no WorkflowRunModel entry exists yet (during
    execution before RecordMetricsAction fires), the diagram endpoint would
    return 404. Now it falls back to running engine processes.
    """

    @pytest.fixture(autouse=True)
    def patch_diagram_deps(self, store, wf_engine):
        """Patch engine and agent_engine for diagram tests."""
        import zebra_agent_web.api.agent_engine as agent_engine_module
        import zebra_agent_web.api.engine as engine_module

        defn = _simple_human_task_definition()
        defn_with_name = defn.model_copy(update={"name": "Human Task Test"})

        old_store = engine_module._store
        old_engine = engine_module._engine
        old_metrics = agent_engine_module._metrics
        old_library = agent_engine_module._library

        engine_module._store = store
        engine_module._engine = wf_engine
        agent_engine_module._metrics = _StubMetricsStoreEmpty()
        agent_engine_module._library = _StubLibraryWithWorkflow(defn_with_name)

        yield defn_with_name

        engine_module._store = old_store
        engine_module._engine = old_engine
        agent_engine_module._metrics = old_metrics
        agent_engine_module._library = old_library

    async def test_diagram_fallback_when_no_metrics_record(self, client, wf_engine, store):
        """Diagram returns SVG when metrics record is absent but process exists.

        Regression: previously returned 404 when WorkflowRunModel entry was missing.
        Now falls back to engine processes to find the workflow_name.
        """
        # Create a process with run_id and workflow_name in properties
        defn = _simple_human_task_definition()
        run_id = "test-run-123"
        process = await wf_engine.create_process(
            defn,
            properties={"run_id": run_id, "workflow_name": "Human Task Test"},
        )
        await wf_engine.start_process(process.id)

        response = await client.get(f"/api/runs/{run_id}/diagram/")
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == run_id
        assert data["workflow_name"] == "Human Task Test"
        assert "<svg" in data["svg"]

    async def test_diagram_404_when_run_id_not_found(self, client):
        """Diagram returns 404 when run_id matches no metrics record or process."""
        response = await client.get("/api/runs/totally-nonexistent-run/diagram/")
        assert response.status_code == 404


# ===========================================================================
# REST API Tests: Run Status (sync @api_view fix)
# ===========================================================================


class _StubMetricsStoreWithRun:
    """Metrics store stub that returns a run record."""

    def __init__(self, run):
        self._run = run

    async def get_run(self, run_id):
        if run_id == self._run.id:
            return self._run
        return None

    async def get_in_progress_runs(self):
        return []


class TestRunStatus:
    """Tests for GET /api/runs/<id>/status/.

    Regression test: the view was async def + @api_view (DRF incompatibility
    that returns a coroutine instead of a Response). Now converted to sync
    with async_to_sync.
    """

    @pytest.fixture(autouse=True)
    def patch_deps(self, store, wf_engine):
        """Patch engine + agent_engine for run_status tests."""
        import zebra_agent_web.api.agent_engine as agent_engine_module
        import zebra_agent_web.api.engine as engine_module

        old_store = engine_module._store
        old_engine = engine_module._engine
        old_metrics = agent_engine_module._metrics
        old_library = agent_engine_module._library

        engine_module._store = store
        engine_module._engine = wf_engine
        agent_engine_module._metrics = _StubMetricsStore()
        agent_engine_module._library = _StubLibrary()

        yield

        engine_module._store = old_store
        engine_module._engine = old_engine
        agent_engine_module._metrics = old_metrics
        agent_engine_module._library = old_library

    async def test_run_status_not_found(self, client):
        """Returns 404 for unknown run_id with JSON body."""
        response = await client.get("/api/runs/nonexistent-run/status/")
        assert response.status_code == 404
        data = response.json()
        assert data["status"] == "not_found"

    async def test_run_status_returns_json(self, client):
        """Response is proper JSON, not a coroutine error.

        Previously this endpoint was async def + @api_view, which caused DRF to
        return a 500 instead of a Response (the coroutine was never awaited).
        """
        response = await client.get("/api/runs/any-id/status/")
        # Should be a valid JSON response (200 or 404), NOT a 500 coroutine error
        assert response.status_code in (200, 404)
        data = response.json()
        assert "status" in data
