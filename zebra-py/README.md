# Zebra Workflow Engine (Python)

A modern Python workflow engine designed for AI-assisted development workflows. Zebra enables Claude and other AI systems to plan and execute complex, long-running development tasks through a structured workflow model.

## Features

- **YAML Workflow Definitions**: Human and AI-readable workflow definitions
- **Parallel Execution**: Support for parallel task branches with synchronization points
- **Pluggable Actions**: Extensible task action system for custom behaviors
- **Persistent State**: SQLite-based persistence for resumable workflows
- **MCP Integration**: Model Context Protocol server for Claude integration
- **Type Safety**: Full type hints with Pydantic models

## Installation

```bash
# Install with uv
uv add zebra-workflow

# With MCP server support
uv add zebra-workflow --extra mcp

# For development
uv sync --extra dev
```

## Quick Start

### Define a Workflow

Create a YAML workflow definition:

```yaml
# my_workflow.yaml
name: "Feature Implementation"
version: 1

tasks:
  gather_requirements:
    name: "Gather Requirements"
    action: prompt
    auto: false
    properties:
      prompt: "What feature should we implement?"

  create_plan:
    name: "Create Plan"
    action: prompt
    auto: false
    properties:
      prompt: "Create a plan for: {{gather_requirements.output}}"

  implement:
    name: "Implement"
    action: shell
    properties:
      command: "echo 'Implementing...'"

routings:
  - from: gather_requirements
    to: create_plan
  - from: create_plan
    to: implement
```

### Run the Workflow

```python
import asyncio
from zebra import WorkflowEngine
from zebra.storage import SQLiteStore
from zebra.tasks import ActionRegistry
from zebra.definitions import load_definition

async def main():
    # Initialize storage and registry
    store = SQLiteStore("workflows.db")
    await store.initialize()

    registry = ActionRegistry()
    registry.register_defaults()

    # Create engine
    engine = WorkflowEngine(store, registry)

    # Load and start workflow
    definition = load_definition("my_workflow.yaml")
    process = await engine.create_process(definition)
    await engine.start_process(process.id)

    # Handle manual tasks
    while True:
        pending = await engine.get_pending_tasks(process.id)
        if not pending:
            break

        task = pending[0]
        print(f"Task: {task.properties.get('__prompt__', 'No prompt')}")
        response = input("Your response: ")

        from zebra.core.models import TaskResult
        await engine.complete_task(task.id, TaskResult.ok(response))

    print("Workflow complete!")

asyncio.run(main())
```

Run with:

```bash
uv run python my_script.py
```

## Workflow Concepts

### Tasks

Tasks are the building blocks of workflows. Each task has:

- **id**: Unique identifier within the workflow
- **name**: Human-readable name
- **action**: Name of the TaskAction to execute
- **auto**: If True, executes automatically; if False, waits for manual completion
- **synchronized**: If True, waits for all incoming parallel branches
- **properties**: Configuration passed to the action

### Routings

Routings define the flow between tasks:

- **from/to**: Source and destination task IDs
- **parallel**: If True, creates a new execution branch
- **condition**: Optional condition to evaluate before routing

### Parallel Execution & Synchronization

Workflows can split into parallel branches and rejoin:

```yaml
tasks:
  start:
    name: Start

  task_a:
    name: Task A

  task_b:
    name: Task B

  join:
    name: Join
    synchronized: true  # Waits for both branches

routings:
  - from: start
    to: task_a
    parallel: true

  - from: start
    to: task_b
    parallel: true

  - from: task_a
    to: join

  - from: task_b
    to: join
```

## Built-in Actions

### shell

Execute shell commands:

```yaml
tasks:
  run_tests:
    name: "Run Tests"
    action: shell
    properties:
      command: "pytest tests/"
      timeout: 300
```

### prompt

Pause for human/AI input:

```yaml
tasks:
  get_input:
    name: "Get Input"
    action: prompt
    auto: false
    properties:
      prompt: "What should we do?"
```

## Custom Actions

Create custom task actions:

```python
from zebra.tasks import TaskAction, TaskResult, ExecutionContext
from zebra.core.models import TaskInstance

class MyCustomAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        # Do something
        result = await do_work(task.properties)
        return TaskResult.ok(output=result)

# Register the action
registry.register_action("my_action", MyCustomAction)
```

## MCP Server

Run the MCP server for Claude integration:

```bash
uv run python -m zebra.mcp.server
```

Available MCP tools:

- `create_workflow`: Create a workflow from YAML
- `start_workflow`: Start a created workflow
- `get_workflow_status`: Get workflow status
- `list_workflows`: List all workflows
- `get_pending_tasks`: Get tasks awaiting input
- `complete_task`: Complete a pending task
- `pause_workflow`: Pause a running workflow
- `resume_workflow`: Resume a paused workflow

## Development

```bash
# Clone and install
git clone <repo>
cd zebra-py
uv sync --extra dev

# Run tests
uv run pytest tests/ -v

# Run linter
uv run ruff check .
```

## Architecture

Zebra is a port of the Java Zebra workflow engine with modernizations:

```
┌─────────────────────────────────────┐
│         MCP Server Layer            │
│  (Claude/AI integration via tools)  │
└─────────────────────────────────────┘
                 │
┌─────────────────────────────────────┐
│       WorkflowEngine                │
│  (Process/Task lifecycle, routing)  │
└─────────────────────────────────────┘
                 │
┌─────────────────────────────────────┐
│       Pluggable Task Actions        │
│  (shell, prompt, custom actions)    │
└─────────────────────────────────────┘
                 │
┌─────────────────────────────────────┐
│       Storage Abstraction           │
│  (SQLite, In-Memory)                │
└─────────────────────────────────────┘
```

## License

Apache License 2.0

## Credits

Based on the Java Zebra workflow engine originally developed by Anite (2004) and modified by Ben Gidley (2010).
