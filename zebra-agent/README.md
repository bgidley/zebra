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

The zebra-agent library can be used in two ways:

### Standalone (In-Memory - Default)
When used directly via CLI, data is stored in memory:
- **Workflows**: Loaded from `~/.zebra-agent/workflows/` (YAML files, persistent)
- **Memory**: Uses `InMemoryMemoryStore` for conversation context (transient)
- **Metrics**: Uses `InMemoryMetricsStore` for workflow statistics (transient)

Note: In-memory data is lost when the process exits. For persistent storage, use zebra-agent-web.

### Web UI (Django ORM)
When used through `zebra-agent-web`, storage is handled by Django's ORM:
- `DjangoMemoryStore` implements the `MemoryStore` interface
- `DjangoMetricsStore` implements the `MetricsStore` interface
- Database backend configured via Django's `DATABASES` setting
