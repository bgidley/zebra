# AGENTS.md - zebra-py (Core Workflow Engine)

This file provides coding agent guidelines specific to the `zebra-py` package - the core workflow engine with MCP integration.

> **Note**: For project-wide guidelines (code style, testing patterns, important rules), see the [root AGENTS.md](../AGENTS.md).

## Package Overview

`zebra-py` is the core workflow engine package containing:
- **Workflow Engine**: Process lifecycle, task state transitions, routing evaluation
- **Storage Layer**: Persistence abstractions (SQLite, In-Memory)
- **MCP Server**: Model Context Protocol integration for Claude
- **Definition Loader**: YAML/JSON workflow parsing

## Core Concepts

### State Machines

**ProcessState**: `created → running → complete` (optionally `paused` or `failed`)  
**TaskState**: `pending → awaiting_sync → ready → running → complete` (or `failed`)

Manual tasks wait in `ready` state until explicitly transitioned. Auto tasks execute immediately.

### Flow of Execution (FOE)

FOE tracks parallel execution branches. Serial routings inherit the parent FOE; parallel routings create new FOEs. Synchronized tasks wait for all incoming FOEs before executing (join point).

### TaskAction Interface

Custom actions implement: `async def run(task: TaskInstance, context: ExecutionContext) -> TaskResult`

Register actions by name in `ActionRegistry`. Actions access task properties, resolve templates, and manipulate process state through the context.

### StateStore Interface

Abstracts persistence layer. Implementations:
- `InMemoryStore` - For testing and simple workflows
- `SQLiteStore` - For production with persistent state

## File Locations

| Directory | Purpose |
|-----------|---------|
| `zebra/core/` | Engine, models, exceptions |
| `zebra/core/engine.py` | Main WorkflowEngine class |
| `zebra/core/models.py` | Pydantic models (ProcessInstance, TaskInstance, etc.) |
| `zebra/core/exceptions.py` | Custom exception hierarchy |
| `zebra/storage/` | StateStore implementations |
| `zebra/storage/memory.py` | InMemoryStore |
| `zebra/storage/sqlite.py` | SQLiteStore |
| `zebra/definitions/` | Workflow definition loading |
| `zebra/definitions/loader.py` | YAML/JSON parser |
| `zebra/tasks/` | TaskAction base classes and registry |
| `zebra/tasks/base.py` | TaskAction, ExecutionContext |
| `zebra/tasks/registry.py` | ActionRegistry |
| `zebra/tasks/actions/` | Built-in actions (shell, prompt) |
| `zebra/mcp/` | MCP server implementation |
| `zebra/templates/` | Example workflow definitions |
| `tests/` | Test suite |

## Module-Specific Commands

```bash
# Run tests for this package only
uv run pytest zebra-py/tests/ -v

# Run single test file
uv run pytest zebra-py/tests/test_engine.py -v

# Run single test function
uv run pytest zebra-py/tests/test_engine.py::test_simple_workflow -v

# Run MCP server
uv run python -m zebra.mcp.server
```

## Common Tasks

### Add a New Task Action

1. Create class in `zebra/tasks/actions/` (or in `zebra-tasks` for reusable actions)
2. Inherit from `TaskAction`
3. Implement `async def run(task, context) -> TaskResult`
4. Register in workflow or `ActionRegistry`
5. Add tests in `tests/`

**Example with template resolution and property access:**

```python
from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, TaskAction

class MyAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        # Access task properties
        value = task.properties.get("my_key")
        
        # Resolve templates from process properties
        resolved = context.resolve_template("{{my_var}}")
        
        # Set process properties for downstream tasks
        context.set_process_property("output_key", result)
        
        return TaskResult.ok(output={"result": result})
```

### Add a New Test

1. Create test file in `tests/` directory
2. Use pytest fixtures for setup
3. Test async code with `async def test_*`
4. Run: `uv run pytest zebra-py/tests/test_file.py -v`

### Debug a Workflow

1. Check process state: `process.state`
2. Check task states: `process.tasks[task_id].state`
3. Review logs: `logger.debug()` statements throughout engine
4. Use `InMemoryStore` for simpler debugging (no DB)

## Extension Points

### Custom TaskActions

Implement the `TaskAction` base class and register with `ActionRegistry`:

```python
from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, TaskAction

class CustomAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        # Your logic here
        return TaskResult.ok(output=result)

# Register
registry.register_action("custom_action", CustomAction)
```

### Custom ConditionActions

Implement `ConditionAction` for routing conditions that evaluate to boolean.

### Custom Storage Backends

Implement the `StateStore` abstract base class to create custom persistence layers beyond SQLite and in-memory storage.

## MCP Server

The MCP server enables Claude to create and manage workflows.

### Running

```bash
uv run python -m zebra.mcp.server
```

### Available Tools

| Tool | Description |
|------|-------------|
| `create_workflow` | Create a workflow from YAML definition |
| `start_workflow` | Start a created workflow |
| `get_workflow_status` | Get current status of a workflow |
| `list_workflows` | List all active workflows |
| `get_pending_tasks` | Get tasks waiting for input |
| `complete_task` | Complete a pending task with a result |
| `pause_workflow` | Pause a running workflow |
| `resume_workflow` | Resume a paused workflow |

### Data Location

Workflows are stored in SQLite at `~/.zebra/workflows.db`.

## Related Documentation

- **[workflows.md](workflows.md)** - Workflow Control-Flow Patterns (43 patterns mapped)
- **[README.md](README.md)** - Python usage guide and YAML definition reference
- **[../DESIGN.md](../DESIGN.md)** - Original Java architecture and design patterns
