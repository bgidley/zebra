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
| `templates/` | Django templates |
| `templates/pages/` | Full page templates |
| `templates/partials/` | Partial templates (HTMX) |
| `templates/components/` | Reusable components |
| `static/` | Static assets (CSS, JS) |
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

## Django Settings

Key settings in `settings.py`:

| Setting | Purpose |
|---------|---------|
| `CHANNEL_LAYERS` | Redis configuration for WebSockets |
| `DATABASES` | Database connection (via Django ORM) |
| `CORS_ALLOWED_ORIGINS` | CORS configuration |
| `REST_FRAMEWORK` | DRF settings |

## Testing

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
# Run all tests
uv run pytest zebra-agent-web/ -v

# Run with Django settings
DJANGO_SETTINGS_MODULE=zebra_agent_web.settings uv run pytest -v
```

## Related Documentation

- **[README.md](README.md)** - Package overview
- **[../zebra-agent/AGENTS.md](../zebra-agent/AGENTS.md)** - Agent framework documentation
- **[../zebra-py/AGENTS.md](../zebra-py/AGENTS.md)** - Core engine documentation
