# zebra-agent-cli

Interactive command-line interface for the Zebra Agent.

## Installation

```bash
# From the workspace root - syncs all packages and creates venv
uv sync --all-packages

# Activate the virtual environment
source .venv/bin/activate
```

## Usage

```bash
# Using uv (recommended) - runs without activating venv
uv run zebra-agent

# Or with activated virtual environment
source .venv/bin/activate
zebra-agent
```

## Commands

| Command | Description |
|---------|-------------|
| `/list` | Show available workflows with descriptions |
| `/stats` | Show usage statistics and recent runs |
| `/memory` | Show memory status and usage |
| `/dream` | Run self-improvement cycle |
| `/help` | Show help message |
| `/quit` | Exit the agent (also: `/exit`, `/q`) |

## Interactive Mode

Simply type your goal or question and press Enter. The agent will:

1. Select the best matching workflow (or create a new one)
2. Execute the workflow
3. Display the results
4. Ask for a rating (1-5) to improve future selections

## Database Configuration

This CLI uses Oracle by default. Set these environment variables:

### Oracle (Default)

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

To use PostgreSQL instead, you'll need to modify the CLI code to import PostgreSQL-backed classes. See the `zebra-agent` README for details.

| Variable | Description | Default |
|----------|-------------|---------|
| `PGHOST` | PostgreSQL host | `localhost` |
| `PGPORT` | PostgreSQL port | `5432` |
| `PGDATABASE` | Database name | `opc` |
| `PGUSER` | Database user | `opc` |
| `PGPASSWORD` | Database password | (none) |

## Architecture

The CLI is a thin wrapper around the `zebra-agent` library:

```
zebra-agent-cli (this package)
    └── zebra-agent (library)
            ├── AgentLoop - workflow selection and execution
            ├── WorkflowLibrary - workflow management
            ├── AgentMemory - short/long-term memory
            └── MetricsStore - usage tracking
```

## Development

```bash
# Run tests
uv run pytest zebra-agent-cli/tests/ -v

# Run linter
uv run ruff check zebra-agent-cli/

# Run with specific database configuration
ORACLE_USERNAME=ZEBRA ORACLE_PASSWORD=secret ORACLE_DSN="..." uv run zebra-agent
```

## License

Apache-2.0
