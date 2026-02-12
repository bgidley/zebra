# AGENTS.md - Coding Agent Guidelines for Zebra Workflow Engine

This file provides coding agents with essential guidelines for working on the Zebra workflow engine codebase.

## External File Loading

CRITICAL: When you encounter a file reference (e.g., @rules/general.md), use your Read tool to load it on a need-to-know basis. They're relevant to the SPECIFIC task at hand.

## MCP 
CRITIAL: When you have MCP available like pycharm use it to discover files, refactor code etc

## Bravery
You are a programmer who fundementally believes in Extreme Programming
- Communication is key - check you understand the goal, and your implementation meets it
- Simplicity - keep it simple, avoid unnecessary complexit
- Feedback - Show and tell, ask for help
- Courage - design and code for today and not for tomorrow, refactor mercilessly
- Respect - quality matters respect your work, keeps tests passing, don't leave a mess for others

## Project Overview

Zebra is a multi-language workflow orchestration system for AI-assisted development with:
- **Python** (primary): Core workflow engine with MCP integration
- **Legacy Java**: Original 2004 implementation (archived, in `legacy/`)
- **UV workspaces**: Monorepo structure with 4 Python packages

## Monorepo Structure

Each package has its own `AGENTS.md` with module-specific guidelines:

| Package | Purpose                                        | AGENTS.md |
|---------|------------------------------------------------|-----------|
| [zebra-py](zebra-py/) | Core workflow engine with MCP integration      | [zebra-py/AGENTS.md](zebra-py/AGENTS.md) |
| [zebra-tasks](zebra-tasks/) | Reusable task actions (LLM, subtasks, compute) | [zebra-tasks/AGENTS.md](zebra-tasks/AGENTS.md) |
| [zebra-agent](zebra-agent/) | Self-improving agent library with cli          | [zebra-agent/AGENTS.md](zebra-agent/AGENTS.md) |
| [zebra-agent-web](zebra-agent-web/) | Web UI for Zebra Agent                         | [zebra-agent-web/AGENTS.md](zebra-agent-web/AGENTS.md) |

## Architecture Overview

The workflow engine follows a layered, interface-driven architecture:

**Workflow Definitions (YAML/JSON)** → **Definition Loaders** → **WorkflowEngine (Core)** → **TaskActions & StateStore**

The engine handles:
- Process lifecycle (create → start → complete)
- Task state transitions (ready → running → complete)
- Routing evaluation (serial vs parallel)
- Synchronization/join points for parallel branches

## Workspace-Level Commands

### Setup & Build

```bash
# Install all Python packages (from project root)
uv sync --all-packages

# Install individual package
cd zebra-py && uv sync
```

### Running Tests

```bash
# Run all Python tests (from project root)
uv run pytest

# Run all tests with coverage
uv run pytest --cov

# Run tests for a specific package
uv run pytest zebra-py/tests/ -v
uv run pytest zebra-tasks/tests/ -v
uv run pytest zebra-agent/tests/ -v

# Run single test file
uv run pytest zebra-py/tests/test_engine.py -v

# Run single test function
uv run pytest zebra-py/tests/test_engine.py::test_simple_workflow -v

# Run tests matching pattern
uv run pytest -k "parallel" -v
```

### Test Environment Configuration

The project uses `pytest-dotenv` to automatically load environment variables from `.env` files before tests run. This is configured in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
env_files = [".env"]
```

This ensures Oracle credentials and API keys are available for integration tests. Do not add manual dotenv loading in conftest files - the plugin handles this automatically.

**Required Environment Variables for Integration Tests:**
- `ORACLE_DSN`, `ORACLE_USERNAME`, `ORACLE_PASSWORD` - Oracle database credentials
- `ANTHROPIC_API_KEY` - For LLM integration tests

### MCP

If you are connected to pycharm MCP like pycharm prefer it's tools over other options

### Linting & Formatting

```bash
# Run Ruff linter (from project root)
uv run ruff check .

# Auto-fix linting issues
uv run ruff check --fix .

# Format code
uv run ruff format .

# Check formatting without changes
uv run ruff format --check .
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
  - `StateError` → `ProcessNotFoundError`, `TaskNotFoundError`, `LockError`, `SerializationError`
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

Don't hack tests to make them pass. Only change them if the business logic has changed, if you are not sure ask.

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
8. **Properties must be JSON-serializable** - All values in process/task properties must be JSON-serializable (strings, numbers, booleans, lists, dicts, and None). This includes `TaskResult.output`, which is stored into process properties. Non-serializable values are rejected at model construction time and will raise `SerializationError` at the storage layer.

9. **Use `ExecutionContext.extras` for non-serializable dependencies** - Pass services like stores and libraries via `context.extras` (engine-level injection) rather than process properties. This is configured when creating the `WorkflowEngine`:

```python
engine = WorkflowEngine(store, registry, extras={
    "__memory_store__": memory_store,
    "__metrics_store__": metrics_store,
    "__workflow_library__": library,
})

# In task actions, retrieve from context.extras:
memory_store = context.extras.get("__memory_store__")
```

## Related Documentation

- **[DESIGN.md](DESIGN.md)** - Original Java architecture and design patterns
- **[zebra-py/README.md](zebra-py/README.md)** - Python usage guide and YAML definition reference
- **[zebra-py/workflows.md](zebra-py/workflows.md)** - Workflow Control-Flow Patterns (43 patterns mapped)
- **[zebra-tasks/README.md](zebra-tasks/README.md)** - Task actions library documentation
- **[zebra-agent/README.md](zebra-agent/README.md)** - Agent framework overview
