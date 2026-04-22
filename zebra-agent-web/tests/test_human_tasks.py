"""Tests for human task web views and REST API.

Tests use InMemoryStore and a real WorkflowEngine (no Django ORM or Oracle),
monkey-patching the engine singleton so views use test fixtures.
"""

from datetime import UTC

import pytest
from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessDefinition, RoutingDefinition, TaskDefinition
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
def client(db):
    """Django async test client, authenticated as a test user."""
    from django.contrib.auth import get_user_model
    from django.test import AsyncClient

    User = get_user_model()
    user = User.objects.create_user(username="testuser")
    c = AsyncClient()
    c.force_login(user)
    return c


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
# Web View Tests: Activity Page Improvements
# ===========================================================================


def _auto_task_only_definition():
    """A workflow with only auto tasks (no human tasks)."""
    return ProcessDefinition(
        id="auto-task-wf",
        name="Auto Task Workflow",
        version=1,
        first_task_id="step1",
        tasks={
            "step1": TaskDefinition(
                id="step1",
                name="Step One",
                auto=True,
            ),
            "step2": TaskDefinition(
                id="step2",
                name="Step Two",
                auto=True,
            ),
        },
        routings=[
            RoutingDefinition(id="r1", source_task_id="step1", dest_task_id="step2"),
        ],
    )


async def _create_running_process_with_auto_task(wf_engine, store, run_id, goal):
    """Create a RUNNING process with only auto tasks in READY state.

    We build the state manually because the engine auto-executes auto tasks,
    so we can't rely on start_process() to leave them in READY state.
    """
    from zebra.core.models import ProcessState, TaskInstance, TaskState

    defn = _auto_task_only_definition()
    await store.save_definition(defn)

    process = await wf_engine.create_process(defn)
    # Manually transition to RUNNING with a READY auto task
    updated = process.model_copy(
        update={
            "state": ProcessState.RUNNING,
            "properties": {"run_id": run_id, "goal": goal},
        }
    )
    await store.save_process(updated)

    # Create a READY auto task
    task = TaskInstance(
        id=f"auto-task-{run_id}",
        task_definition_id="step1",
        process_id=process.id,
        state=TaskState.READY,
        foe_id=f"foe-{run_id}",
    )
    await store.save_task(task)

    return process, task


class TestActivityAutoTasks:
    """Tests for showing running processes with only non-human tasks."""

    async def test_running_process_with_auto_tasks_shown(self, client, wf_engine, store):
        """A running process with only auto tasks still appears on activity page.

        Even with human_only=true (default), the *group* should appear — only
        the task list is filtered. Previously, groups were silently dropped
        when all pending tasks were auto tasks.
        """
        await _create_running_process_with_auto_task(
            wf_engine, store, "test-auto-run", "Run auto tasks"
        )

        # Default view (human_only=true)
        response = await client.get("/activity/")
        assert response.status_code == 200
        # The group should appear even without visible tasks
        assert b"Run auto tasks" in response.content
        assert b"running" in response.content

    async def test_auto_tasks_visible_when_human_only_false(self, client, wf_engine, store):
        """With human_only=false, auto tasks appear in the task list."""
        await _create_running_process_with_auto_task(
            wf_engine, store, "test-auto-visible", "Show auto tasks"
        )

        response = await client.get("/activity/?human_only=false")
        assert response.status_code == 200
        assert b"Step One" in response.content
        assert b"ready" in response.content


class _ConfigurableMetricsStore:
    """Metrics store stub with configurable completed runs."""

    def __init__(self, completed_runs=None, in_progress_runs=None):
        self._completed = completed_runs or []
        self._in_progress = in_progress_runs or []

    async def get_in_progress_runs(self):
        return self._in_progress

    async def get_completed_runs(self, limit=20):
        return self._completed[:limit]

    async def get_recent_runs(self, limit=10):
        return self._completed[:limit]

    async def get_run(self, run_id):
        return next((r for r in self._completed if r.id == run_id), None)

    async def get_task_executions(self, run_id):
        return []


class TestActivityRecentCompletions:
    """Tests for showing recent completed runs by default."""

    async def test_recent_completions_shown_without_toggle(self, client, store, wf_engine):
        """Completed runs appear on /activity/ without show_completed=true."""
        from datetime import datetime

        import zebra_agent_web.api.agent_engine as agent_engine_module
        from zebra_agent.metrics import WorkflowRun

        completed_run = WorkflowRun(
            id="test-recent-run",
            workflow_name="Answer Question",
            goal="What is the meaning of life?",
            success=True,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            tokens_used=100,
        )
        agent_engine_module._metrics = _ConfigurableMetricsStore(completed_runs=[completed_run])

        # Default view — no show_completed toggle
        response = await client.get("/activity/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "What is the meaning of life?" in content
        assert "Answer Question" in content
        assert "success" in content

    async def test_show_full_history_label(self, client):
        """The toggle label says 'Show full history' not 'Include completed'."""
        response = await client.get("/activity/")
        assert response.status_code == 200
        assert b"Show full history" in response.content
        assert b"Include completed" not in response.content


class TestActivityStaleness:
    """Tests for stale running process detection."""

    async def test_stale_process_marked_in_response(self, client, wf_engine, store):
        """A running process with old updated_at gets the 'stale' badge."""
        from datetime import datetime, timedelta

        defn = _simple_human_task_definition()
        process = await wf_engine.create_process(defn)
        await wf_engine.start_process(process.id)

        # Make the process look stale (updated 48 hours ago)
        run_id = "test-stale-run-id"
        running_process = await store.load_process(process.id)
        stale_time = datetime.now(UTC) - timedelta(hours=48)
        updated = running_process.model_copy(
            update={
                "properties": {"run_id": run_id, "goal": "Old stale goal"},
                "updated_at": stale_time,
            }
        )
        await store.save_process(updated)

        response = await client.get("/activity/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "stale" in content.lower()
        assert "Old stale goal" in content

    async def test_fresh_process_not_marked_stale(self, client, wf_engine, store):
        """A recently updated running process does NOT get the stale badge."""
        defn = _simple_human_task_definition()
        process = await wf_engine.create_process(defn)
        await wf_engine.start_process(process.id)

        run_id = "test-fresh-run-id"
        running_process = await store.load_process(process.id)
        updated = running_process.model_copy(
            update={
                "properties": {"run_id": run_id, "goal": "Fresh goal"},
            }
        )
        await store.save_process(updated)

        response = await client.get("/activity/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "Fresh goal" in content
        # Should NOT have the stale section header or badge for this process
        assert "Stale" not in content

    async def test_section_headers_rendered(self, client, wf_engine, store):
        """Activity page renders section headers for different group types."""
        defn = _simple_human_task_definition()
        process = await wf_engine.create_process(defn)
        await wf_engine.start_process(process.id)

        response = await client.get("/activity/")
        assert response.status_code == 200
        content = response.content.decode()
        # Should have "In Progress" section header for the running process
        assert "In Progress" in content


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
            "/api/tasks/nonexistent/complete/",
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


# ===========================================================================
# API Tests: Process Cancel / Delete
# ===========================================================================


class TestProcessCancel:
    """Tests for POST /api/processes/<id>/cancel/."""

    async def test_cancel_running_process(self, client, wf_engine, store):
        """Cancelling a running process moves it to FAILED state."""
        defn = _simple_human_task_definition()
        process, _ = await _start_workflow(wf_engine, defn)

        response = await client.post(
            f"/api/processes/{process.id}/cancel/",
            data={"reason": "Test cancel"},
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["cancelled"] is True
        assert data["state"] == "failed"

        # Verify persisted
        reloaded = await store.load_process(process.id)
        assert reloaded.state.value == "failed"
        assert reloaded.properties["__error__"] == "Test cancel"

    async def test_cancel_already_completed_returns_409(self, client, wf_engine):
        """Cancelling an already-completed process returns 409 Conflict."""
        from zebra.core.models import ProcessDefinition, TaskDefinition

        # Use a simple auto-completing workflow
        defn = ProcessDefinition(
            id="auto-wf",
            name="Auto",
            version=1,
            first_task_id="step",
            tasks={"step": TaskDefinition(id="step", name="Step", auto=True)},
            routings=[],
        )
        process = await wf_engine.create_process(defn)
        await wf_engine.start_process(process.id)

        response = await client.post(
            f"/api/processes/{process.id}/cancel/",
            content_type="application/json",
        )
        assert response.status_code == 409

    async def test_cancel_not_found_returns_404(self, client):
        """Cancelling a non-existent process returns 404."""
        response = await client.post(
            "/api/processes/nonexistent-id/cancel/",
            content_type="application/json",
        )
        assert response.status_code == 404

    async def test_cancel_default_reason(self, client, wf_engine, store):
        """When no reason is provided, a default reason is used."""
        defn = _simple_human_task_definition()
        process, _ = await _start_workflow(wf_engine, defn)

        response = await client.post(
            f"/api/processes/{process.id}/cancel/",
            content_type="application/json",
        )
        assert response.status_code == 200

        reloaded = await store.load_process(process.id)
        assert reloaded.properties["__error__"] == "Cancelled by user"


class TestProcessDelete:
    """Tests for DELETE /api/processes/<id>/delete/."""

    async def test_delete_process(self, client, wf_engine, store):
        """Deleting a process removes it from the store."""
        defn = _simple_human_task_definition()
        process, _ = await _start_workflow(wf_engine, defn)

        response = await client.delete(f"/api/processes/{process.id}/delete/")
        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] is True

        # Verify it's gone
        reloaded = await store.load_process(process.id)
        assert reloaded is None

    async def test_delete_not_found_returns_404(self, client):
        """Deleting a non-existent process returns 404."""
        response = await client.delete("/api/processes/nonexistent-id/delete/")
        assert response.status_code == 404

    async def test_delete_removes_tasks(self, client, wf_engine, store):
        """Deleting a process also removes its tasks."""
        defn = _simple_human_task_definition()
        process, pending = await _start_workflow(wf_engine, defn)
        task_id = pending[0].id

        await client.delete(f"/api/processes/{process.id}/delete/")

        # Task should also be gone
        task = await store.load_task(task_id)
        assert task is None
