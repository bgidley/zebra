# Zebra Web UI

Web-based interface for Zebra workflow management.

## Features

- **REST API** for workflow definitions, processes, and tasks
- **WebSocket** support for real-time updates
- **React frontend** for visualization and monitoring (coming soon)

## Quick Start

### Install Dependencies

```bash
cd zebra-web
uv pip install -e .
```

### Run the Development Server

```bash
# Using Daphne (ASGI server with WebSocket support)
uv run daphne -b 127.0.0.1 -p 8000 zebra_web.asgi:application

# Or using Django's runserver (no WebSocket support)
uv run python manage.py runserver
```

### API Endpoints

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
| GET | `/api/processes/{id}/tasks/` | Get tasks for process |
| GET | `/api/tasks/` | Get all pending tasks |
| GET | `/api/tasks/{id}/` | Get task details |
| POST | `/api/tasks/{id}/complete/` | Complete pending task |

### WebSocket

Connect to `ws://localhost:8000/ws/` for real-time updates.

**Subscribe to specific channels:**
```javascript
ws.send(JSON.stringify({action: "subscribe", channel: "process_abc123"}));
```

**Event types:**
- `process_updated` - Process state changed
- `task_updated` - Task state changed
- `definition_created` - New workflow definition created
- `definition_deleted` - Workflow definition deleted

## Configuration

Environment variables:
- `DJANGO_SECRET_KEY` - Secret key for Django
- `DJANGO_DEBUG` - Set to "0" for production
- `PGHOST` - PostgreSQL host (default: `/var/run/postgresql`)
- `PGPORT` - PostgreSQL port (default: 5432)
- `PGDATABASE` - Database name (default: opc)
- `PGUSER` - Database user (default: opc)
- `PGPASSWORD` - Database password (optional for peer auth)

## Architecture

```
zebra-web/
├── manage.py                # Django management script
├── zebra_web/
│   ├── settings.py         # Django settings
│   ├── urls.py             # Root URL config
│   ├── asgi.py             # ASGI application (WebSocket)
│   └── api/
│       ├── views.py        # REST API views
│       ├── serializers.py  # DRF serializers
│       ├── consumers.py    # WebSocket consumers
│       ├── engine.py       # Zebra engine singleton
│       └── urls.py         # API URL config
└── frontend/               # React frontend (coming soon)
```

## Development

### Running Tests

```bash
uv run pytest
```

### Code Style

The project uses Ruff for linting and formatting:

```bash
uv run ruff check .
uv run ruff format .
```
