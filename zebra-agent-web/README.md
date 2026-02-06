# Zebra Agent Web

Web UI for Zebra Agent - goal-driven workflow automation.

## Features

- **Run Goal** - Enter natural language goals and watch them execute
- **In-Progress Runs** - Monitor currently executing goals with live workflow diagrams
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
- **`nav_item.html`** - Navigation sidebar items

### Static Assets

- **`static/js/workflow-diagram.js`** - Shared JavaScript for diagram auto-refresh

## License

Apache-2.0
