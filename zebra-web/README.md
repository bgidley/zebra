# Zebra Web UI

Web-based interface for Zebra workflow management using Django Templates + HTMX + Alpine.js (the "HOT stack").

## Features

- **Dashboard** with health status and stats
- **Workflow Definitions** - Create, view, delete workflow definitions from YAML
- **Process Management** - Start, pause, resume, delete workflow processes
- **Task Completion** - Complete pending manual tasks
- **Real-time Updates** via HTMX polling
- **REST API** for programmatic access

## Quick Start

### Prerequisites

- PostgreSQL running with a database (default: `opc`)
- Python 3.11+

### Install Dependencies

```bash
# From the project root directory
cd /path/to/zebra

# Install zebra-workflow first (required dependency)
uv pip install -e zebra-py/

# Install zebra-web
uv pip install -e zebra-web/
```

### Run the Server

```bash
# Local development (localhost only)
uv run zebra-serve

# Remote access (Tailscale, etc.)
uv run zebra-serve-public
```

Then open http://localhost:8000 (or your remote IP)

### Available Commands

| Command | Description |
|---------|-------------|
| `uv run zebra-serve` | Start server on localhost:8000 |
| `uv run zebra-serve-public` | Start server on 0.0.0.0:8000 (remote access) |

## Tech Stack

- **Django** - Web framework
- **Django REST Framework** - JSON API
- **HTMX** - Dynamic updates without JavaScript
- **Alpine.js** - Lightweight reactivity for modals/interactions
- **Tailwind CSS** (CDN) - Styling

## API Endpoints

The JSON API is still available at `/api/`:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health/` | Health check |
| GET | `/api/definitions/` | List all workflow definitions |
| POST | `/api/definitions/` | Create definition from YAML |
| GET | `/api/definitions/{id}/` | Get definition details |
| DELETE | `/api/definitions/{id}/` | Delete definition |
| GET | `/api/processes/` | List process instances |
| POST | `/api/processes/` | Start new process |
| GET | `/api/processes/{id}/` | Get process details with tasks |
| DELETE | `/api/processes/{id}/` | Delete process |
| POST | `/api/processes/{id}/pause/` | Pause running process |
| POST | `/api/processes/{id}/resume/` | Resume paused process |
| GET | `/api/tasks/` | Get all pending tasks |
| POST | `/api/tasks/{id}/complete/` | Complete pending task |

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DJANGO_SECRET_KEY` | (dev key) | Secret key for Django |
| `DJANGO_DEBUG` | `1` | Set to `0` for production |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated allowed hosts |
| `PGHOST` | `/var/run/postgresql` | PostgreSQL host |
| `PGPORT` | `5432` | PostgreSQL port |
| `PGDATABASE` | `opc` | Database name |
| `PGUSER` | `opc` | Database user |
| `PGPASSWORD` | (none) | Database password |

### PostgreSQL Setup

```bash
# Initialize PostgreSQL (if not done)
sudo /usr/pgsql-16/bin/postgresql-16-setup initdb
sudo systemctl start postgresql-16
sudo systemctl enable postgresql-16

# Create user and database
sudo -u postgres createuser -s opc
sudo -u postgres createdb -O opc opc
```

## Architecture

```
zebra-web/
├── pyproject.toml          # Python package config
├── manage.py               # Django management script
├── templates/              # Django templates
│   ├── base.html          # Base layout with nav
│   ├── pages/             # Full page templates
│   ├── partials/          # HTMX partial templates
│   └── components/        # Reusable components
└── zebra_web/
    ├── settings.py         # Django settings
    ├── urls.py             # URL routing
    ├── cli.py              # CLI entry points
    └── api/
        ├── views.py        # REST API views (JSON)
        ├── web_views.py    # Web UI views (HTML)
        ├── serializers.py  # DRF serializers
        └── engine.py       # Zebra engine singleton
```
