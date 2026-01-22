# AGENTS.md - Coding Agent Guidelines for Zebra Workflow Engine

This file provides coding agents with essential guidelines for working on the Zebra workflow engine codebase.

## Project Overview

Zebra is a multi-language workflow orchestration system for AI-assisted development with:
- **Python** (primary): Core workflow engine with MCP integration
- **Rust**: High-performance alternative implementation
- **Legacy Java**: Original 2004 implementation (archived, in `legacy/`)
- **UV workspaces**: Monorepo structure with 3 Python packages (zebra-py, zebra-tasks, zebra-agent)

## Architecture

The workflow engine follows a layered, interface-driven architecture:

**Workflow Definitions (YAML/JSON)** → **Definition Loaders** → **WorkflowEngine (Core)** → **TaskActions & StateStore**

The engine handles:
- Process lifecycle (create → start → complete)
- Task state transitions (ready → running → complete)
- Routing evaluation (serial vs parallel)
- Synchronization/join points for parallel branches

### Core Components

| Component | Python | Rust |
|-----------|--------|------|
| Engine | `zebra/core/engine.py` | `src/core/engine.rs` |
| Models | `zebra/core/models.py` | `src/core/models.rs` |
| Storage | `zebra/storage/` | `src/storage/` |
| Actions | `zebra/tasks/` | `src/tasks/` |
| Loader | `zebra/definitions/loader.py` | `src/definitions/` |

Subprojects have thier own AGENTS.md files.

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

## Build & Test Commands

### Setup & Build

```bash
# Install all Python packages (from project root)
uv sync --all-packages

# Install individual package
cd zebra-py && uv sync

# Build Rust package
cd zebra-rs && cargo build --release
```

### Running Tests

```bash
# Run all Python tests (from project root)
uv run pytest

# Run all tests with coverage
uv run pytest --cov

# Run single test file
uv run pytest zebra-py/tests/test_engine.py -v

# Run single test function
uv run pytest zebra-py/tests/test_engine.py::test_simple_workflow -v

# Run tests matching pattern
uv run pytest -k "parallel" -v

# Run Rust tests
cd zebra-rs && cargo test

# Run single Rust test
cd zebra-rs && cargo test test_engine -- --nocapture

# Run Rust performance tests (release mode)
cd zebra-rs && cargo test --release perf_
```

### Linting & Formatting

```bash
# Python: Run Ruff linter (from project root)
uv run ruff check .

# Python: Auto-fix linting issues
uv run ruff check --fix .

# Python: Format code
uv run ruff format .

# Python: Check formatting without changes
uv run ruff format --check .

# Rust: Linting
cd zebra-rs && cargo clippy

# Rust: Check formatting
cd zebra-rs && cargo fmt --check

# Rust: Auto-format
cd zebra-rs && cargo fmt
```

### Running MCP Server

```bash
cd zebra-py
uv run python -m zebra.mcp.server
```

## Code Style Guidelines

### Python Style (Ruff Configuration)

**Line Length**: 100 characters  
**Target Python**: 3.11+  
**Linting Rules**: E (errors), F (pyflakes), I (import sorting), UP (upgrade syntax)

### Import Organization

Imports are organized in 4 groups with blank lines between:

```python
# 1. Standard library
import logging
import uuid
from datetime import datetime, timezone

# 2. Third-party packages
from pydantic import BaseModel, Field

# 3. Zebra core modules
from zebra.core.models import ProcessInstance, TaskResult
from zebra.core.exceptions import ExecutionError
from zebra.tasks.base import ExecutionContext, TaskAction

# 4. Current package (if applicable)
from zebra_tasks.llm.base import LLMProvider, Message
```

Use absolute imports only. Avoid relative imports.

### Type Annotations

**Always use type hints** for function signatures:

```python
# Good
async def create_process(
    self,
    definition: ProcessDefinition,
    properties: dict | None = None,
    parent_process_id: str | None = None,
) -> ProcessInstance:
    """Create a new process instance."""
    ...

# Use modern union syntax (Python 3.11+)
def get_value(key: str) -> str | None:
    ...

# Not: Optional[str], Union[str, None]
```

**Use `Any` sparingly** - prefer specific types when possible.

### Naming Conventions

- **Classes**: `PascalCase` (e.g., `WorkflowEngine`, `TaskDefinition`)
- **Functions/Methods**: `snake_case` (e.g., `create_process`, `execute_task`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `MAX_RETRIES`)
- **Private members**: Prefix with `_` (e.g., `_task_sync`, `_build_messages`)
- **Module-level private**: Single `_` prefix (e.g., `_utc_now()`)

### Docstrings

Use Google-style docstrings for all public APIs:

```python
async def create_process(
    self,
    definition: ProcessDefinition,
    properties: dict | None = None,
) -> ProcessInstance:
    """Create a new process instance from a definition.

    The process is created in CREATED state and must be started
    with start_process() to begin execution.

    Args:
        definition: The process definition to instantiate
        properties: Initial process properties (merged with definition defaults)

    Returns:
        The created ProcessInstance in CREATED state

    Raises:
        ValidationError: If the definition is invalid
    """
```

Module-level docstrings should explain the module's purpose:

```python
"""Core workflow engine implementation.

This module contains the WorkflowEngine class that controls the execution
of workflow processes. Ported from Java Engine class.
"""
```

### Error Handling

**Use custom exceptions** from `zebra.core.exceptions`:

```python
from zebra.core.exceptions import (
    ProcessNotFoundError,
    TaskExecutionError,
    InvalidStateTransitionError,
)

# Raise specific exceptions
if process is None:
    raise ProcessNotFoundError(f"Process {process_id} not found")

# Return TaskResult for task action errors
if provider is None:
    return TaskResult.fail("No LLM provider available")
```

**Exception hierarchy**:
- `ZebraError` (base for all Zebra exceptions)
  - `DefinitionError` → `DefinitionNotFoundError`, `ValidationError`
  - `StateError` → `ProcessNotFoundError`, `TaskNotFoundError`, `LockError`
  - `ExecutionError` → `TaskExecutionError`, `RoutingError`, `ActionError`

### Async/Await

All engine operations are async. Use `async def` and `await`:

```python
# Good
async def start_process(self, process_id: str) -> None:
    process = await self.store.get_process(process_id)
    await self._transition_process(process, ProcessState.RUNNING)

# Always await async calls - don't forget!
result = await provider.complete(messages=messages)
```

### Pydantic Models

Use Pydantic for all data models:

```python
class TaskDefinition(BaseModel):
    """Definition of a task within a workflow."""

    id: str = Field(..., description="Unique identifier")
    name: str = Field(..., description="Human-readable name")
    auto: bool = Field(default=True, description="Auto-execute flag")
    properties: dict[str, Any] = Field(
        default_factory=dict,
        description="Task-specific configuration"
    )

    model_config = {"frozen": True}  # Make immutable
```

### Logging

Use module-level logger:

```python
import logging

logger = logging.getLogger(__name__)

# Use appropriate log levels
logger.debug("Task %s transitioning to %s", task.id, new_state)
logger.info("Process %s completed successfully", process_id)
logger.warning("Retry attempt %d/%d", attempt, max_retries)
logger.error("Failed to execute task: %s", error)
```

## Testing Guidelines

### Test Structure

Use pytest with fixtures:

```python
@pytest.fixture
def store():
    return InMemoryStore()

@pytest.fixture
def registry():
    reg = ActionRegistry()
    reg.register_action("counting", CountingAction)
    return reg

@pytest.fixture
def engine(store, registry):
    return WorkflowEngine(store, registry)
```

### Test Actions

Create simple test actions:

```python
class CountingAction(TaskAction):
    """A test action that counts executions."""

    execution_count = 0

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        CountingAction.execution_count += 1
        return TaskResult.ok(output={"count": CountingAction.execution_count})
```

### Async Tests

Tests are automatically async with `pytest-asyncio` (asyncio_mode = "auto"):

```python
async def test_simple_workflow(engine, simple_definition):
    process = await engine.create_process(simple_definition)
    await engine.start_process(process.id)
    
    process = await engine.store.get_process(process.id)
    assert process.state == ProcessState.COMPLETE
```

### Test Coverage

Coverage is configured to:
- Track branch coverage
- Exclude MCP server and `__main__.py` files
- Show missing lines
- Exclude TYPE_CHECKING blocks, abstract methods, and "pragma: no cover"

## Important Rules

1. **Don't make tests pass by cheating** - Tests must verify real functionality
2. **Always write tests for code** - New features require corresponding tests
3. **Use UV for Python** - This is a UV-based project, not pip/poetry/conda
4. **Maintain backward compatibility** - This is a library; API changes affect users
5. **Follow the state machine** - Process and task states have specific valid transitions
6. **Use ActionRegistry** - All task actions must be registered before use
7. **Handle async properly** - Engine is fully async; don't block the event loop

## File Locations

- **Core engine**: `zebra-py/zebra/core/`
- **Task actions**: `zebra-tasks/zebra_tasks/`
- **Tests**: `zebra-py/tests/`, `zebra-tasks/tests/`, `zebra-agent/tests/`
- **Config**: `pyproject.toml` (workspace root and each package)
- **Examples**: `zebra-py/zebra/templates/`

## Common Tasks

### Add a New Task Action

1. Create class in `zebra-tasks/zebra_tasks/`
2. Inherit from `TaskAction`
3. Implement `async def run(task, context) -> TaskResult`
4. Register in workflow or `ActionRegistry`
5. Add tests in `zebra-tasks/tests/`

**Example with template resolution and property access:**

```python
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

1. Create test file in appropriate `tests/` directory
2. Use pytest fixtures for setup
3. Test async code with `async def test_*`
4. Run: `uv run pytest path/to/test_file.py -v`

### Debug a Workflow

1. Check process state: `process.state`
2. Check task states: `process.tasks[task_id].state`
3. Review logs: `logger.debug()` statements throughout engine
4. Use `InMemoryStore` for simpler debugging (no DB)

## Extension Points

### Custom TaskActions

Implement the `TaskAction` base class and register with `ActionRegistry`:

```python
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

Implement the `StateStore` abstract base class (Python) or trait (Rust) to create custom persistence layers beyond SQLite and in-memory storage.

## Related Documentation

- **design.md** - Original Java architecture and design patterns
- **zebra-py/README.md** - Python usage guide and YAML definition reference
- **zebra-py/workflows.md** - Workflow Control-Flow Patterns (43 patterns mapped)
- **zebra-tasks/README.md** - Task actions library documentation
- **zebra-agent/DESIGN.md** - Agent framework design overview
