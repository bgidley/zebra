# Zebra Agent

Self-improving agent console that uses zebra workflows to achieve goals.

## Features

- **Workflow-Based Architecture**: The entire agent loop is a declarative Zebra workflow
- **Workflow Selection**: LLM-powered selection of the best workflow for your goal
- **Workflow Creation**: Automatically creates new workflows when no match exists
- **Performance Tracking**: Tracks success rates and user ratings for continuous improvement
- **Expanding Library**: Each interaction can expand the workflow library
- **Memory Management**: Two-tier memory system with automatic compaction

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

## Architecture

### Workflow-Based Agent Loop

The agent loop is implemented as a declarative Zebra workflow (`agent_main_loop.yaml`),
not imperative Python code. This design ensures:

- **Composability**: Each step is a reusable task action
- **Visibility**: The flow is visible and editable as YAML  
- **Testability**: Steps can be individually tested
- **Extensibility**: Easy to add new steps or modify the flow

### How It Works

The "Agent Main Loop" workflow orchestrates the following steps:

```
check_memory
    |
    +--[needs short-term compaction]--> compact_short_term --> select_workflow
    +--[needs long-term compaction]---> compact_long_term --> select_workflow
    +--[no compaction needed]---------> select_workflow
                                            |
                                            +--[create_new]--> create_workflow --> execute_workflow
                                            +--[use_existing]-----------------> execute_workflow
                                                                                    |
                                                                                    v
                                                                              record_metrics
                                                                                    |
                                                                                    v
                                                                              update_memory
```

**Steps:**

1. **Memory Check**: Check if memory needs compaction
2. **Memory Compaction**: Run short-term or long-term compaction if needed
3. **Workflow Selection**: LLM selects the best workflow for the goal
4. **Workflow Creation**: If no match, LLM creates a new workflow
5. **Execution**: Run the selected/created workflow
6. **Metrics Recording**: Record run metrics for analytics
7. **Memory Update**: Add interaction to agent memory

### Task Actions

The agent loop uses these task actions (from `zebra-tasks`):

| Action | Purpose |
|--------|---------|
| `memory_check` | Check if memory needs compaction, sets routing |
| `workflow_selector` | LLM-powered workflow selection |
| `workflow_creator` | LLM-powered workflow creation |
| `execute_goal_workflow` | Execute a workflow by name |
| `record_metrics` | Record run to metrics store |
| `update_memory` | Add entry to agent memory |

### IoC (Inversion of Control)

Stores are passed to task actions via process properties:
- `__memory_store__`: Agent memory store
- `__metrics_store__`: Metrics tracking store  
- `__workflow_library__`: Workflow library for loading definitions

This allows actions to be stateless and testable with mock stores.

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

## System Workflows

The following workflows are internal and excluded from selection:

| Workflow | Purpose |
|----------|---------|
| `Agent Main Loop` | Main orchestration workflow |
| `Memory Compact Short` | Short-term memory compaction |
| `Memory Compact Long` | Long-term memory compaction |
