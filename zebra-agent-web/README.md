# Zebra Agent Web

Web UI for Zebra Agent - goal-driven workflow automation.

## Installation

```bash
# From the workspace root - syncs all packages and creates venv
uv sync --all-packages

# Activate the virtual environment
source .venv/bin/activate
```

## Database Configuration

This web application uses Oracle by default for both Django's database and the Zebra workflow engine.

### Oracle (Default)

Set these environment variables before running the server:

```bash
export ORACLE_USERNAME="ZEBRA"
export ORACLE_PASSWORD="your_password"
export ORACLE_DSN="(description=(address=(protocol=tcps)(port=1522)(host=your-host.oraclecloud.com))(connect_data=(service_name=your_service.adb.oraclecloud.com)))"
# Optional: for mTLS with Oracle Cloud Wallet
export ORACLE_WALLET_LOCATION="/path/to/wallet"
export ORACLE_WALLET_PASSWORD="wallet_password"
```

**Environment Variables:**

| Variable | Description | Required |
|----------|-------------|----------|
| `ORACLE_USERNAME` | Oracle database user | Yes |
| `ORACLE_PASSWORD` | Oracle database password | Yes |
| `ORACLE_DSN` | Oracle connection string (TNS) | Yes |
| `ORACLE_WALLET_LOCATION` | Path to Oracle wallet (for mTLS) | Optional |
| `ORACLE_WALLET_PASSWORD` | Wallet password (if encrypted) | Optional |

### PostgreSQL (Alternative)

To use PostgreSQL instead, modify `zebra_agent_web/settings.py`:

```python
# Change DATABASES to use PostgreSQL
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("PGDATABASE", "zebra"),
        "USER": os.environ.get("PGUSER", "zebra"),
        "PASSWORD": os.environ.get("PGPASSWORD", ""),
        "HOST": os.environ.get("PGHOST", "localhost"),
        "PORT": os.environ.get("PGPORT", "5432"),
    }
}

# Update ZEBRA_SETTINGS and ZEBRA_AGENT_SETTINGS to use PostgreSQL
ZEBRA_SETTINGS = {
    "POSTGRES_HOST": os.environ.get("PGHOST", "localhost"),
    "POSTGRES_PORT": int(os.environ.get("PGPORT", "5432")),
    "POSTGRES_DATABASE": os.environ.get("PGDATABASE", "zebra"),
    "POSTGRES_USER": os.environ.get("PGUSER", "zebra"),
    "POSTGRES_PASSWORD": os.environ.get("PGPASSWORD", None),
}
```

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

## Development

```bash
# Run tests
uv run pytest zebra-agent-web/tests/ -v

# Run linter
uv run ruff check zebra-agent-web/

# Run with specific configuration
ORACLE_USERNAME=ZEBRA ORACLE_PASSWORD=secret uv run zebra-web-agent-dev
```

## License

Apache-2.0
