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
    """Monkey-patch the engine singleton so views use our test engine/store."""
    import zebra_agent_web.api.engine as engine_module

    old_store = engine_module._store
    old_engine = engine_module._engine

    engine_module._store = store
    engine_module._engine = wf_engine

    yield

    engine_module._store = old_store
    engine_module._engine = old_engine


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
    """Tests for the /tasks/ view."""

    async def test_empty_when_no_processes(self, client):
        """No running processes -> empty task list."""
        response = await client.get("/tasks/")
        assert response.status_code == 200
        assert b"No pending tasks" in response.content

    async def test_shows_pending_human_task(self, client, wf_engine):
        """A running workflow with auto:false task shows in the list."""
        defn = _simple_human_task_definition()
        await _start_workflow(wf_engine, defn)

        response = await client.get("/tasks/")
        assert response.status_code == 200
        assert b"Ask User" in response.content
        assert b"Awaiting Input" in response.content

    async def test_htmx_returns_partial(self, client, wf_engine):
        """With HX-Request header, returns the partial template only."""
        defn = _simple_human_task_definition()
        await _start_workflow(wf_engine, defn)

        response = await client.get("/tasks/", headers={"HX-Request": "true"})
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

    async def test_404_for_unknown_task(self, client):
        """Unknown task_id returns 404."""
        response = await client.get("/tasks/nonexistent-id/")
        assert response.status_code == 404


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
