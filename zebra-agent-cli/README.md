# zebra-agent-cli

Interactive command-line interface for the Zebra Agent.

## Installation

```bash
# From the workspace root
uv sync --all-packages

# Or install directly
uv pip install zebra-agent-cli
```

## Usage

```bash
# Start the interactive CLI
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

## Environment Variables

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
```

## License

Apache-2.0
