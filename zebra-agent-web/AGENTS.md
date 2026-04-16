# AGENTS.md - zebra-agent-web (Web UI)

This file provides coding agent guidelines specific to the `zebra-agent-web` package - Web UI for Zebra Agent.

> **Note**: For project-wide guidelines (code style, testing patterns, important rules), see the [root AGENTS.md](../AGENTS.md).

## Package Overview

`zebra-agent-web` is a Django-based web application providing:
- **REST API**: For workflow and agent interactions
- **WebSocket Support**: Real-time updates via Django Channels
- **Web Interface**: Browser-based UI for the agent console

## Technology Stack

- **Django 5.0+**: Web framework
- **Django REST Framework**: REST API
- **Django Channels**: WebSocket support
- **Daphne**: ASGI server
- **Channels Redis**: WebSocket channel layer
- **Django ORM**: Database abstraction (PostgreSQL, Oracle, SQLite via Django)

## File Locations

| Directory | Purpose |
|-----------|---------|
| `zebra_agent_web/` | Django project root |
| `zebra_agent_web/settings.py` | Django settings |
| `zebra_agent_web/urls.py` | URL routing |
| `zebra_agent_web/asgi.py` | ASGI application |
| `zebra_agent_web/cli.py` | CLI entry points |
| `zebra_agent_web/api/` | API application |
| `zebra_agent_web/api/views.py` | REST API views |
| `zebra_agent_web/api/web_views.py` | Web page views |
| `zebra_agent_web/api/consumers.py` | WebSocket consumers |
| `zebra_agent_web/api/routing.py` | WebSocket routing |
| `zebra_agent_web/api/serializers.py` | DRF serializers |
| `zebra_agent_web/api/urls.py` | API URL routing |
| `zebra_agent_web/api/engine.py` | Engine integration |
| `zebra_agent_web/api/agent_engine.py` | Agent engine wrapper (creates BudgetManager + injection) |
| `zebra_agent_web/api/daemon.py` | Shared daemon loop (`run_daemon_loop()`) |
| `zebra_agent_web/storage.py` | DjangoStore (StateStore for workflow state) |
| `zebra_agent_web/memory_store.py` | DjangoMemoryStore (MemoryStore for agent memory) |
| `zebra_agent_web/metrics_store.py` | DjangoMetricsStore (MetricsStore for metrics) |
| `zebra_agent_web/api/models.py` | Django models for workflow data |
| `zebra_agent_web/diagram.py` | Workflow SVG diagram generator |
| `templates/` | Django templates |
| `templates/pages/` | Full page templates |
| `templates/partials/` | Partial templates (HTMX) |
| `templates/pages/run_pending.html` | Queued/running/completed/failed process detail (no metrics record) |
| `templates/components/` | Reusable components |
| `static/` | Static assets (CSS, JS) |
| `static/js/workflow-diagram.js` | Shared workflow diagram JavaScript |
| `manage.py` | Django management script |

## Module-Specific Commands

```bash
# Run development server (localhost only)
zebra-web-agent-dev

# Run development server (public access)
zebra-web-agent-dev-public

# Run production server (localhost only)
zebra-web-agent

# Run production server (public access)
zebra-web-agent-public

# Or using manage.py directly
uv run python manage.py runserver
uv run python manage.py migrate
uv run python manage.py collectstatic

# Run tests
uv run pytest zebra-agent-web/ -v
```

## Common Tasks

### Add a New API Endpoint

1. Define serializer in `api/serializers.py` (if needed)
2. Create view in `api/views.py`
3. Add URL route in `api/urls.py`

**Example:**

```python
# api/serializers.py
from rest_framework import serializers

class WorkflowStatusSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    state = serializers.CharField()
    progress = serializers.FloatField()

# api/views.py
from rest_framework.views import APIView
from rest_framework.response import Response

class WorkflowStatusView(APIView):
    def get(self, request, workflow_id):
        # Get workflow status from engine
        status = self.get_workflow_status(workflow_id)
        serializer = WorkflowStatusSerializer(status)
        return Response(serializer.data)

# api/urls.py
urlpatterns = [
    path("workflows/<str:workflow_id>/status/", WorkflowStatusView.as_view()),
]
```

### Add a New WebSocket Consumer

1. Create consumer in `api/consumers.py`
2. Add routing in `api/routing.py`

**Example:**

```python
# api/consumers.py
from channels.generic.websocket import AsyncJsonWebsocketConsumer

class WorkflowProgressConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.workflow_id = self.scope["url_route"]["kwargs"]["workflow_id"]
        self.group_name = f"workflow_{self.workflow_id}"
        
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def workflow_update(self, event):
        await self.send_json(event["data"])

# api/routing.py
websocket_urlpatterns = [
    re_path(r"ws/workflow/(?P<workflow_id>\w+)/$", WorkflowProgressConsumer.as_asgi()),
]
```

### Add a New Web Page

1. Create template in `templates/pages/`
2. Add view in `api/web_views.py`
3. Add URL route in `urls.py`

**Example:**

```python
# api/web_views.py
from django.shortcuts import render

def workflow_list(request):
    workflows = get_workflows()  # From engine
    return render(request, "pages/workflow_list.html", {"workflows": workflows})

# urls.py
urlpatterns = [
    path("workflows/", web_views.workflow_list, name="workflow_list"),
]
```

### Add HTMX Partial

For dynamic updates without full page reload:

```html
<!-- templates/partials/workflow_status.html -->
<div id="workflow-status" hx-swap-oob="true">
    <span class="status-{{ workflow.state }}">{{ workflow.state }}</span>
    <span>{{ workflow.progress }}%</span>
</div>
```

```python
# api/web_views.py
def workflow_status_partial(request, workflow_id):
    workflow = get_workflow(workflow_id)
    return render(request, "partials/workflow_status.html", {"workflow": workflow})
```

### Add Reusable Template Partial

For shared components used across multiple pages:

1. Create template in `templates/partials/`
2. Use `{% include %}` with parameters

**Example - Workflow Diagram Component:**

```html
<!-- templates/partials/workflow_diagram.html -->
{% comment %}
Parameters passed via include:
  - run_id: The run ID to fetch diagram for
  - workflow_name: Workflow name to display
  - auto_refresh: "true" or "false" (string, not boolean)
  - show_header: "true" or "false" (string, not boolean)
{% endcomment %}

<div class="workflow-diagram-component" 
     data-run-id="{{ run_id }}"
     data-auto-refresh="{{ auto_refresh|default:'false' }}">
    <!-- diagram content -->
</div>
```

**Usage:**

```html
<!-- In another template -->
{% include "partials/workflow_diagram.html" with run_id=run.id auto_refresh="true" show_header="false" %}
```

**Important Template Rules:**

1. **Use `{% comment %}` for documentation** - HTML comments (`<!-- -->`) do NOT prevent Django template tags from being parsed
2. **Pass booleans as strings** - Use `show_header="false"` not `show_header=False` to avoid template resolution issues
3. **Check for string values** - Use `{% if show_header != "false" %}` instead of `{% if show_header %}`

## Django Settings

Key settings in `settings.py`:

| Setting | Purpose |
|---------|---------|
| `CHANNEL_LAYERS` | Redis configuration for WebSockets |
| `DATABASES` | Database connection (via Django ORM) |
| `CORS_ALLOWED_ORIGINS` | CORS configuration |
| `REST_FRAMEWORK` | DRF settings |
| `ZEBRA_AGENT_SETTINGS.DAEMON_AUTO_START` | Auto-start budget daemon in ASGI server (default: true) |
| `ZEBRA_AGENT_SETTINGS.DAILY_BUDGET_USD` | Daily LLM spend limit (default: 50.00) |
| `ZEBRA_AGENT_SETTINGS.DAEMON_POLL_INTERVAL` | Seconds between daemon queue polls (default: 30) |
| `ZEBRA_AGENT_SETTINGS.BUDGET_RESET_HOUR` | Hour (UTC) when daily budget resets (default: 0) |
| `ZEBRA_AGENT_SETTINGS.GOAL_COST_WARNING_USD` | Per-goal soft warning threshold (default: 5.00) |

## Async Views and DRF

### DRF API Views with Async

Django REST Framework's `@api_view` decorator has issues with async views. If you need to call async functions from an API view, use a sync view with `async_to_sync`:

```python
from asgiref.sync import async_to_sync
from rest_framework.decorators import api_view
from rest_framework.response import Response

def _get_data_impl(run_id):
    """Sync helper that uses async_to_sync internally."""
    async def _get_data():
        await agent_engine.ensure_initialized()
        metrics = agent_engine.get_metrics()
        return await metrics.get_run(run_id)
    
    return async_to_sync(_get_data)()

@api_view(["GET"])
def my_api_view(request, run_id):
    """Sync view that calls async functions via async_to_sync."""
    data = _get_data_impl(run_id)
    if data is None:
        return Response({"error": "Not found"}, status=404)
    return Response({"data": data})
```

**Do NOT use `async def` with `@api_view`** - it will return a coroutine instead of a Response.

### Web Views (Non-DRF)

Regular Django web views can be async:

```python
async def my_web_view(request):
    await agent_engine.ensure_initialized()
    data = await get_async_data()
    return render(request, "pages/my_page.html", {"data": data})
```

## Querying the Database Directly

You can query the Oracle database directly from a script for debugging and investigation. Use the environment variables from `.env` and Django's ORM via a standalone script:

```bash
cd /home/opc/projects/zebra/zebra-agent-web && \
  ORACLE_USERNAME=ZEBRA \
  ORACLE_PASSWORD=<from .env> \
  ORACLE_DSN='<from .env>' \
  DJANGO_SETTINGS_MODULE=zebra_agent_web.settings \
  uv run python -c "
import django
django.setup()
from zebra_agent_web.api.models import (
    ProcessInstanceModel,
    TaskInstanceModel,
    FlowOfExecutionModel,
    WorkflowRunModel,
    TaskExecutionModel,
)
import json

# Example: find all READY tasks
for t in TaskInstanceModel.objects.filter(state='READY').order_by('-updated_at')[:10]:
    print(t.id, t.task_definition_id, t.process_id, t.state)
"
```

**Key model names** (all in `zebra_agent_web/api/models.py`):

| Model | Table purpose | Useful fields |
|-------|--------------|---------------|
| `ProcessInstanceModel` | Workflow process instances | `id`, `definition_id`, `state`, `properties` (JSON string), `updated_at` |
| `TaskInstanceModel` | Task instances within a process | `id`, `task_definition_id`, `process_id`, `state`, `result` (JSON), `error`, `updated_at` |
| `FlowOfExecutionModel` | Flow-of-execution tokens | `id`, `process_id` |
| `WorkflowRunModel` | Agent-level run records (metrics) | `id`, `goal`, `workflow_name`, `success`, `started_at`, `completed_at`, `output`, `error` |
| `TaskExecutionModel` | Per-task execution records within a run | `id`, `run` (FK), `task_definition_id`, `task_name`, `state`, `output`, `error` |

**Notes:**
- `properties` and `result` fields are JSON strings — use `json.loads()` to parse them
- Process states: `running`, `complete`, `failed`
- Task states: `READY`, `running`, `failed` (note READY is uppercase in the DB)
- The `.env` file is at the project root (`/home/opc/projects/zebra/.env`) — read it to get credentials

## Debugging

Prefer the Python debugger (`pdb`) over adding debug logging statements. Insert a breakpoint directly in the code under investigation:

```python
import pdb; pdb.set_trace()
```

Or use the built-in shorthand (Python 3.7+):

```python
breakpoint()
```

Then run the server or test in the foreground so the debugger attaches to your terminal. Remove the breakpoint once done — don't leave debug statements in committed code.

## Testing

### Test Environment Setup

Integration tests require a real Oracle database connection. Environment variables are automatically loaded from `.env` via `pytest-dotenv` (configured in root `pyproject.toml`):

```toml
[tool.pytest.ini_options]
env_files = [".env"]
```

**Required `.env` variables:**
- `ORACLE_DSN` - Oracle connection string (using TLS/TCPS protocol)
- `ORACLE_USERNAME` - Database username
- `ORACLE_PASSWORD` - Database password
- `ANTHROPIC_API_KEY` - For LLM integration tests

### Test Structure

```python
import pytest
from django.test import TestCase
from rest_framework.test import APIClient

@pytest.mark.django_db
class TestWorkflowAPI:
    def test_get_workflow_status(self, api_client):
        response = api_client.get("/api/workflows/test-id/status/")
        assert response.status_code == 200
        assert "state" in response.json()

@pytest.fixture
def api_client():
    return APIClient()
```

### Running Tests

```bash
# Run all tests (excludes Oracle integration tests by default)
uv run pytest zebra-agent-web/ -v

# Run specific test file
uv run pytest zebra-agent-web/tests/test_diagram.py -v

# Run Oracle integration tests (requires real database)
uv run pytest zebra-agent-web/tests/test_agent_loop_integration.py -v

# Run with Django settings
DJANGO_SETTINGS_MODULE=zebra_agent_web.settings uv run pytest -v
```

### Integration Tests

The `test_agent_loop_integration.py` tests run the complete agent workflow against a real Oracle database and make actual LLM API calls. These tests:

- Verify end-to-end workflow from goal to completion
- Test real metrics persistence in Oracle
- Test real memory storage in Oracle
- Make actual Anthropic API calls

**Note:** These tests do NOT clean up after themselves - records persist in Oracle for inspection.

## Key Components

### Engine Initialization (`api/engine.py`)

The engine uses `IoCActionRegistry` from `zebra-agent` for automatic task action
discovery via entry points, replacing the previous ~40 lines of manual
`register_action()` calls:

```python
from zebra_agent.ioc import ZebraContainer, IoCActionRegistry

container = ZebraContainer()
# Register services into container as needed...

registry = IoCActionRegistry(container)
registry.discover_and_register()  # auto-discovers all zebra-tasks entry points

engine = WorkflowEngine(store, registry)
```

This means adding new task actions to `zebra-tasks` (with entry points in its
`pyproject.toml`) automatically makes them available in the web UI without any
code changes in `zebra-agent-web`.

### Budget Daemon (`api/daemon.py` + `asgi.py`)

The daemon auto-starts as a background `asyncio.create_task()` inside the ASGI server on first HTTP/WebSocket request via `DaemonStarterMiddleware` in `asgi.py`. It can also run standalone via `python manage.py run_daemon`.

**Loop:** `pick_next() → budget_check → start_process → poll until done → log cost → repeat`

- `DaemonStarterMiddleware`: ASGI middleware that wraps the Daphne application; on first request, spawns the daemon task. Controlled by `DAEMON_AUTO_START` setting.
- `run_daemon_loop()`: Shared reusable daemon loop in `api/daemon.py`, used by both the middleware and the management command.
- Daphne does **not** support ASGI lifespan protocol, hence the first-request middleware approach.

### Orphaned Process Visibility

When a daemon-executed goal fails before `assess_and_record` runs, no `WorkflowRunModel` is created. The activity view (`web_views.py`) handles this by:

1. Querying the process store for COMPLETE/FAILED processes with a `run_id` property
2. Filtering out those that already have a `WorkflowRunModel`
3. Rendering them in the activity list with `success=False` and task history from `__task_output_*` process properties

The `run_detail` view also has a `_run_detail_pending_fallback()` that searches all 4 process states (CREATED, RUNNING, COMPLETE, FAILED) to render process info from properties instead of returning 404.

### Workflow Diagram (`diagram.py`)

Generates SVG workflow visualizations showing:
- Task nodes with state coloring (pending, running, complete, failed)
- Execution order badges
- Parallel/serial flow edges
- Clickable tasks that scroll to detail panels

**Usage:**

```python
from zebra_agent_web.diagram import generate_workflow_svg

svg = generate_workflow_svg(workflow_definition, task_executions)
```

### Workflow Diagram JavaScript (`static/js/workflow-diagram.js`)

Shared client-side component for live diagram updates:

```javascript
// Initialize all diagrams on page
WorkflowDiagram.initAll();

// Or create manually
const diagram = new WorkflowDiagram(element);
diagram.start();  // Begin auto-refresh
diagram.stop();   // Stop auto-refresh
diagram.refresh(); // Manual refresh
```

### Human Task Forms (`zebra.forms` + Template Tags)

The web UI renders human task forms from JSON Schema definitions stored in `task_def.properties.schema`. The form system has two layers:

**Server-side form model** (`zebra.forms` in `zebra-py`):
- `schema_to_form(schema)` converts JSON Schema to `FormSchema` (list of `FormField` dataclasses)
- `validate_form_data(schema, data)` validates against JSON Schema constraints (required, minLength, enum, etc.)
- `coerce_form_data(schema, raw_data)` converts HTML form strings to proper Python types

**Django template tag** (`zebra_agent_web/api/templatetags/form_tags.py`):
- `{% load form_tags %}` then `{% render_schema_form form field_errors submitted_values %}` renders the form as Tailwind-styled HTML
- Supports: text, textarea, number, select, checkbox, multiselect, email, url, date inputs
- Shows per-field validation errors, required markers, descriptions, placeholders

**Templates:**
- `partials/human_task_form.html` - HTMX form partial (renders form, route buttons, Submit)
- `partials/human_task_complete.html` - Success partial after submission (HTMX swap)
- `pages/human_task.html` - Full page wrapper with breadcrumb
- `pages/pending_tasks.html` - Lists all pending human tasks across processes
- `partials/pending_tasks_list.html` - HTMX-swappable task list

### Human Task Completion API

The `POST /api/tasks/<task_id>/complete/` endpoint allows external callers to complete human (manual) tasks. This supports the convention-based `auto: false` pattern where `properties.schema` contains JSON Schema for form rendering.

**Request:**

```json
POST /api/tasks/<task_id>/complete/
{
    "result": {"field1": "value1", "field2": "value2"},
    "next_route": "yes"
}
```

- `result` - Dict of form field values (default: `{}`)
- `next_route` (optional) - Route name for conditional routing after completion

**Response:**

```json
{
    "completed": true,
    "task_id": "<task_id>",
    "result": {"field1": "value1", "field2": "value2"},
    "new_tasks": [{"id": "...", "task_definition_id": "...", "state": "..."}]
}
```

**Workflow:** External callers first use `GET /api/processes/<id>/pending-tasks/` to find pending human tasks (enriched with task definition and form schema), render UI accordingly, then POST to this endpoint with the user's response.

### URL Routes

| URL | View | Purpose |
|-----|------|---------|
| `/` | `dashboard` | Main dashboard (includes budget status card) |
| `/run/` | `run_goal_form` | Goal input form (includes priority/deadline/queue options) |
| `/run/execute/` | `run_goal_execute` | Start goal execution |
| `/run/queue/` | `run_goal_queue` | Queue goal for deferred daemon execution |
| `/runs/` | `recent_runs` | Run history |
| `/runs/in-progress/` | `in_progress_runs` | Currently running goals |
| `/runs/<id>/` | `run_detail` | Run details with diagram (includes cost column) |
| `/workflows/` | `workflow_library` | Workflow library |
| `/tasks/` | `pending_tasks` | Pending human tasks list |
| `/tasks/<id>/` | `human_task_form` | Human task form page |
| `/tasks/<id>/submit/` | `human_task_submit` | Submit human task form (POST) |
| `/api/processes/<id>/pending-tasks/` | `process_pending_tasks` | Get pending human tasks with schema (API) |
| `/api/runs/<id>/diagram/` | `run_diagram` | Get workflow diagram SVG (API) |
| `/api/tasks/<id>/complete/` | `task_complete` | Complete a human/manual task (API) |
| `/api/budget/` | `budget_status` | Get budget status JSON (API) |

### WebSocket Routes

| URL | Consumer | Purpose |
|-----|----------|---------|
| `/ws/goal/<run_id>/` | `GoalExecutionConsumer` | Real-time goal execution updates |

## Related Documentation

- **[README.md](README.md)** - Package overview
- **[../zebra-agent/AGENTS.md](../zebra-agent/AGENTS.md)** - Agent framework documentation
- **[../zebra-py/AGENTS.md](../zebra-py/AGENTS.md)** - Core engine documentation
