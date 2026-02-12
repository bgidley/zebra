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
| `zebra_agent_web/api/agent_engine.py` | Agent engine wrapper |
| `zebra_agent_web/storage.py` | DjangoStore (StateStore for workflow state) |
| `zebra_agent_web/memory_store.py` | DjangoMemoryStore (MemoryStore for agent memory) |
| `zebra_agent_web/metrics_store.py` | DjangoMetricsStore (MetricsStore for metrics) |
| `zebra_agent_web/api/models.py` | Django models for workflow data |
| `zebra_agent_web/diagram.py` | Workflow SVG diagram generator |
| `templates/` | Django templates |
| `templates/pages/` | Full page templates |
| `templates/partials/` | Partial templates (HTMX) |
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

### URL Routes

| URL | View | Purpose |
|-----|------|---------|
| `/` | `dashboard` | Main dashboard |
| `/run/` | `run_goal_form` | Goal input form |
| `/run/execute/` | `run_goal_execute` | Start goal execution |
| `/runs/` | `recent_runs` | Run history |
| `/runs/in-progress/` | `in_progress_runs` | Currently running goals |
| `/runs/<id>/` | `run_detail` | Run details with diagram |
| `/workflows/` | `workflow_library` | Workflow library |
| `/api/runs/<id>/diagram/` | `run_diagram` | Get workflow diagram SVG (API) |

### WebSocket Routes

| URL | Consumer | Purpose |
|-----|----------|---------|
| `/ws/goal/<run_id>/` | `GoalExecutionConsumer` | Real-time goal execution updates |

## Related Documentation

- **[README.md](README.md)** - Package overview
- **[../zebra-agent/AGENTS.md](../zebra-agent/AGENTS.md)** - Agent framework documentation
- **[../zebra-py/AGENTS.md](../zebra-py/AGENTS.md)** - Core engine documentation
