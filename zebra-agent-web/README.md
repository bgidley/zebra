# Zebra Agent Web

Web UI for Zebra Agent - goal-driven workflow automation.

## Features

- **Run Goal** - Enter natural language goals and watch them execute
- **In-Progress Runs** - Monitor currently executing goals with live workflow diagrams
- **Human Task Forms** - Fill in structured forms when workflows need human input
- **Run History** - View completed runs with execution details
- **Workflow Library** - Browse and manage workflow definitions
- **Live Workflow Visualization** - SVG diagrams show task progress in real-time
- **WebSocket Updates** - Real-time progress updates during execution

## Installation

```bash
# From the workspace root - syncs all packages and creates venv
uv sync --all-packages

# Activate the virtual environment
source .venv/bin/activate
```

## Database Configuration

Storage is handled by Django's ORM. The application uses Django models for both workflow state persistence and metrics tracking.

### Storage Implementation

This package implements the storage interfaces defined in `zebra-agent`:

- **`zebra_agent_web/api/models.py`** - Django models for all storage data
- **`zebra_agent_web/storage.py`** - `DjangoStore` (StateStore for workflow state)
- **`zebra_agent_web/memory_store.py`** - `DjangoMemoryStore` (MemoryStore for agent memory)
- **`zebra_agent_web/metrics_store.py`** - `DjangoMetricsStore` (MetricsStore for metrics)

### Database Backend

Configure your database backend via the standard Django `DATABASES` setting in `zebra_agent_web/settings.py`.

**Example configurations:**

```python
# Oracle
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.oracle",
        "NAME": os.environ.get("ORACLE_DSN", ""),
        "USER": os.environ.get("ORACLE_USERNAME", ""),
        "PASSWORD": os.environ.get("ORACLE_PASSWORD", ""),
    }
}

# PostgreSQL
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "zebra",
        "USER": "zebra",
        "PASSWORD": os.environ.get("PGPASSWORD", ""),
        "HOST": "localhost",
        "PORT": "5432",
    }
}

# SQLite (for development)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
```

See Django documentation for other database backends.

## Usage

### Development Server

```bash
# Using uv (recommended)
uv run zebra-web-agent-dev

# Or with activated virtual environment
source .venv/bin/activate
zebra-web-agent-dev

# Access the web UI at http://localhost:8000
```

### Production Server

```bash
# Using uv
uv run zebra-web-agent

# Or with activated virtual environment
source .venv/bin/activate
zebra-web-agent
```

### Django Management Commands

```bash
# Using uv
uv run python zebra-agent-web/manage.py migrate
uv run python zebra-agent-web/manage.py collectstatic
uv run python zebra-agent-web/manage.py runserver

# Or with activated virtual environment
source .venv/bin/activate
python zebra-agent-web/manage.py migrate
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DJANGO_SECRET_KEY` | Django secret key | (dev key) |
| `DJANGO_DEBUG` | Enable debug mode | `1` (enabled) |
| `DJANGO_ALLOWED_HOSTS` | Allowed hosts | `localhost,127.0.0.1` |
| `ZEBRA_LIBRARY_PATH` | Workflow library path | `~/.zebra/workflows` |
| `ZEBRA_LLM_PROVIDER` | LLM provider | `anthropic` |
| `ZEBRA_LLM_MODEL` | LLM model | (provider default) |

## Web Pages

| URL | Description |
|-----|-------------|
| `/` | Dashboard with quick actions and recent activity |
| `/run/` | Enter a goal to execute |
| `/runs/in-progress/` | View all currently running goals with live diagrams |
| `/runs/` | Browse run history |
| `/runs/<id>/` | View run details with workflow diagram |
| `/workflows/` | Browse workflow library |
| `/tasks/` | View all pending human tasks across running workflows |
| `/tasks/<id>/` | Fill in and submit a human task form |

## Human Task Forms

When a workflow reaches a task with `auto: false`, the engine pauses and waits for a person to provide input. The web UI renders these as structured forms based on JSON Schema definitions in the workflow YAML.

### How It Works

1. A running workflow hits a human task and pauses.
2. The task appears on the **Pending Tasks** page (`/tasks/`).
3. Clicking a task opens its form page (`/tasks/<id>/`).
4. The form fields, labels, and validation rules are all driven by the JSON Schema in the task definition -- no custom templates needed.
5. On submit, the data is validated server-side. Errors are shown inline. On success, the workflow resumes.

### What the User Sees

The **Pending Tasks** page lists all human tasks waiting for input across every running workflow. Each entry shows the task name, workflow name, and a link to the form.

The form page shows:

- A title and description from the JSON Schema
- Input fields matching the schema (text, textarea, dropdowns, checkboxes, etc.)
- Required field markers and inline validation errors
- Route buttons (e.g. "yes" / "no") when the task has conditional routing, or a generic Submit button otherwise

### Supported Field Types

Forms are rendered from standard JSON Schema. See the [zebra-py README](../zebra-py/README.md#supported-field-types) for the full widget mapping table.

### REST API

The web UI also exposes a JSON API for programmatic access:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/processes/<id>/pending-tasks/` | GET | List pending human tasks for a process, with schema |
| `/api/tasks/<id>/complete/` | POST | Complete a task with `{"result": {...}, "next_route": "..."}` |

### Template Tags

For developers extending the web UI, the `{% render_schema_form %}` template tag renders a `FormSchema` as Tailwind-styled HTML:

```html
{% load form_tags %}
{% render_schema_form form field_errors %}
```

This tag is used internally by `partials/human_task_form.html` and can be reused in custom templates.

## Development

```bash
# Run tests
uv run pytest zebra-agent-web/tests/ -v

# Run linter
uv run ruff check zebra-agent-web/

# Run with specific configuration
uv run zebra-web-agent-dev
```

## Architecture

### Templates

- **`templates/pages/`** - Full page templates extending `base.html`
- **`templates/partials/`** - Reusable partial templates for HTMX updates
- **`templates/components/`** - Small reusable UI components

### Key Partials

- **`workflow_diagram.html`** - Reusable workflow visualization component
- **`goal_processing.html`** - Live goal execution progress UI
- **`human_task_form.html`** - JSON Schema-driven form for human tasks (HTMX)
- **`human_task_complete.html`** - Success state after form submission (HTMX swap)
- **`pending_tasks_list.html`** - List of pending human tasks (HTMX)
- **`nav_item.html`** - Navigation sidebar items

### Static Assets

- **`static/js/workflow-diagram.js`** - Shared JavaScript for diagram auto-refresh

## License

Apache-2.0
