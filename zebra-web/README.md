# Zebra Web UI

Web-based interface for Zebra workflow management.

## Features

- **REST API** for workflow definitions, processes, and tasks
- **WebSocket** support for real-time updates
- **React frontend** for visualization and monitoring

## Quick Start

### Prerequisites

- PostgreSQL running with a database (default: `opc`)
- Node.js 22+ (for frontend development)

### Install Dependencies

```bash
# From the project root directory
cd /path/to/zebra

# Install zebra-workflow first (required dependency)
uv pip install -e zebra-py/

# Install zebra-web
uv pip install -e zebra-web/

# Install frontend dependencies
cd zebra-web/frontend
npm install
```

### Run Development Servers

**Local development (localhost only)**

```bash
uv run zebra-dev
```

This starts both backend (port 8000) and frontend (port 3000). Open http://localhost:3000

**Remote access (Tailscale, SSH tunnels, etc.)**

```bash
uv run zebra-dev-public
```

This binds both servers to all interfaces. Open http://<your-ip>:3000

### Available Commands

| Command | Description |
|---------|-------------|
| `uv run zebra-dev` | Start both servers on localhost (recommended) |
| `uv run zebra-dev-public` | Start both servers on all interfaces |
| `uv run zebra-serve` | Start backend only on localhost:8000 |
| `uv run zebra-serve-public` | Start backend only on 0.0.0.0:8000 |

## API Endpoints

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

### Query Parameters

**GET /api/processes/**
- `include_completed=true` - Include completed processes
- `definition_id=<id>` - Filter by definition
- `state=<state>` - Filter by state (running, paused, complete, failed)

### Example: Create and Run a Workflow

```bash
# Create a workflow definition
curl -X POST http://localhost:8000/api/definitions/ \
  -H "Content-Type: application/json" \
  -d '{"yaml_content": "name: Hello World\nversion: 1\nfirst_task: start\ntasks:\n  start:\n    name: Start\n    properties:\n      message: Hello!"}'

# Start a process (use the definition ID from above)
curl -X POST http://localhost:8000/api/processes/ \
  -H "Content-Type: application/json" \
  -d '{"definition_id": "<definition-id>", "properties": {}}'
```

## WebSocket

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
| `PGPASSWORD` | (none) | Database password (optional for peer auth) |

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
├── pyproject.toml          # Python package config with UV scripts
├── manage.py               # Django management script
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
└── frontend/               # React frontend
    ├── src/
    │   ├── api/            # API client and types
    │   ├── components/     # Reusable components
    │   └── pages/          # Page components
    └── package.json
```

## Development

### Running Tests

```bash
uv run pytest
```

### Code Style

```bash
# Python (Ruff)
uv run ruff check .
uv run ruff format .

# TypeScript (ESLint)
cd frontend && npm run lint
```

### Building for Production

```bash
# Build frontend
cd frontend && npm run build

# The built files will be in frontend/dist/
# Configure Django to serve these in production
```
