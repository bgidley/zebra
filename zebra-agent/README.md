# Zebra Agent

Self-improving agent console that uses zebra workflows to achieve goals.

## Features

- **Workflow Selection**: LLM-powered selection of the best workflow for your goal
- **Workflow Creation**: Automatically creates new workflows when no match exists
- **Performance Tracking**: Tracks success rates and user ratings for continuous improvement
- **Expanding Library**: Each interaction can expand the workflow library

## Installation

```bash
# From the zebra workspace root
uv sync --all-packages

# Or activate the virtual environment
source .venv/bin/activate
```

## Usage

```bash
# Start the interactive console
zebra-agent

# Or run directly
python -m zebra_agent.cli
```

## Commands

- `/list` - Show available workflows
- `/stats` - Show workflow statistics
- `/help` - Show help
- `/quit` - Exit

## Example

```
> What is the capital of France?

  [Using workflow: Answer Question]

  The capital of France is Paris.

  Rate this result (1-5, or Enter to skip): 5
  Thanks for the feedback!

> Brainstorm ideas for a birthday party

  [Using workflow: Brainstorm Ideas]

  ...
```

## How It Works

1. **Goal Input**: You provide a goal or question
2. **Workflow Selection**: The agent uses an LLM to select the best matching workflow
3. **Workflow Creation**: If no good match, a new workflow is created
4. **Execution**: The workflow runs through the zebra engine
5. **Rating**: You can rate the result to improve future selection

## Configuration

Data is stored in `~/.zebra-agent/`:
- `workflows/` - Workflow YAML definitions
- `state.db` - Workflow execution state
- `metrics.db` - Performance metrics

### Database Configuration

This package supports both Oracle and PostgreSQL backends for persistent storage (memory and metrics).

#### Oracle (Default)

Set these environment variables:

```bash
export ORACLE_USERNAME="ZEBRA"
export ORACLE_PASSWORD="your_password"
export ORACLE_DSN="(description=(address=(protocol=tcps)(port=1522)(host=your-host.oraclecloud.com))(connect_data=(service_name=your_service.adb.oraclecloud.com)))"
# Optional: for mTLS with Oracle Cloud Wallet
export ORACLE_WALLET_LOCATION="/path/to/wallet"
export ORACLE_WALLET_PASSWORD="wallet_password"
```

#### PostgreSQL (Alternative)

If you prefer PostgreSQL, modify your code to use the PostgreSQL-backed classes instead:

```python
from zebra_agent.memory import AgentMemory  # PostgreSQL version
from zebra_agent.metrics import MetricsStore  # PostgreSQL version
from zebra.storage.postgres import PostgreSQLStore  # PostgreSQL version

# Then configure with PostgreSQL connection details
memory = AgentMemory(
    host="localhost",
    port=5432,
    database="zebra",
    user="zebra",
    password="your_password"
)
metrics = MetricsStore(
    host="localhost",
    port=5432,
    database="zebra",
    user="zebra",
    password="your_password"
)
store = PostgreSQLStore(
    host="localhost",
    port=5432,
    database="zebra",
    user="zebra",
    password="your_password"
)
```

**Environment variables for PostgreSQL:**
- `PGHOST` - PostgreSQL host (default: `localhost`)
- `PGPORT` - PostgreSQL port (default: `5432`)
- `PGDATABASE` - Database name (default: `opc`)
- `PGUSER` - Database user (default: `opc`)
- `PGPASSWORD` - Database password
