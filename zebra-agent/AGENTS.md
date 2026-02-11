# AGENTS.md - zebra-agent (Agent Framework)

This file provides coding agent guidelines specific to the `zebra-agent` package - a self-improving agent console that uses zebra workflows to achieve goals.

> **Note**: For project-wide guidelines (code style, testing patterns, important rules), see the [root AGENTS.md](../AGENTS.md).

## Package Overview

`zebra-agent` is an interactive agent console that:
- **Workflow Selection**: Uses LLM to select the best workflow for a given goal
- **Workflow Creation**: Automatically creates new workflows when no match exists
- **Performance Tracking**: Tracks success rates and user ratings for continuous improvement
- **Expanding Library**: Each interaction can expand the workflow library

## File Locations

| Directory | Purpose |
|-----------|---------|
| `zebra_agent/` | Package root |
| `zebra_agent/cli.py` | Interactive console CLI |
| `zebra_agent/loop.py` | Main agent loop logic |
| `zebra_agent/library.py` | Workflow library management |
| `zebra_agent/metrics.py` | Metrics dataclasses |
| `zebra_agent/memory.py` | Memory dataclasses |
| `zebra_agent/storage/` | Pluggable storage backends |
| `zebra_agent/storage/interfaces.py` | Abstract storage interfaces (MemoryStore, MetricsStore) |
| `zebra_agent/storage/memory.py` | InMemoryMemoryStore implementation |
| `zebra_agent/storage/metrics.py` | InMemoryMetricsStore implementation |
| `zebra_agent/ioc/` | IoC (Inversion of Control) module |
| `zebra_agent/ioc/container.py` | `ZebraContainer` - dependency injection container |
| `zebra_agent/ioc/registry.py` | `IoCActionRegistry` - action registry with constructor injection |
| `zebra_agent/ioc/discovery.py` | Entry point discovery for task actions and conditions |
| `workflows/` | Built-in workflow definitions |
| `tests/` | Test suite |

## Data Storage

### Storage Architecture
zebra-agent uses pluggable storage interfaces defined in `zebra_agent/storage/interfaces.py`:
- `MemoryStore`: Interface for agent memory (short-term/long-term)
- `MetricsStore`: Interface for workflow metrics tracking

### Standalone Usage (In-Memory - Default)
When used directly via the CLI, in-memory implementations are used:

| Component | Implementation | Persistence |
|-----------|---------------|-------------|
| Workflows | File-based (`~/.zebra-agent/workflows/`) | Persistent (YAML files) |
| Memory | `InMemoryMemoryStore` | Transient (lost on exit) |
| Metrics | `InMemoryMetricsStore` | Transient (lost on exit) |

### Web Usage (Django ORM)
When used through `zebra-agent-web`, Django ORM implementations are used:
- `DjangoMemoryStore` implements `MemoryStore`
- `DjangoMetricsStore` implements `MetricsStore`
- Database backend configured via Django's `DATABASES` setting

## Module-Specific Commands

```bash
# Run tests for this package only
uv run pytest zebra-agent/tests/ -v

# Run single test file
uv run pytest zebra-agent/tests/test_loop.py -v

# Run the agent CLI
uv run python -m zebra_agent.cli

# Or if installed as package
zebra-agent
```

## Architecture

### Workflow-Based Agent Loop

The agent loop is implemented as a **declarative Zebra workflow** (`workflows/agent_main_loop.yaml`),
not imperative Python code. The `AgentLoop` class is a thin wrapper that runs this workflow.

**Design Benefits:**
- **Composability**: Each step is a reusable task action
- **Visibility**: The entire flow is visible and editable as YAML
- **Testability**: Steps can be individually unit tested
- **Extensibility**: Easy to add new steps or modify the flow

### Agent Main Loop Workflow

The workflow handles the complete goal processing flow:

```
check_memory
    |
    +--[compact_short]--> compact_short_term --> select_workflow
    +--[compact_long]---> compact_long_term --> select_workflow
    +--[continue]-------> select_workflow
                              |
                              +--[create_new]--> create_workflow --> execute_workflow
                              +--[use_existing]----------------> execute_workflow
                                                                      |
                                                                      v
                                                                record_metrics
                                                                      |
                                                                      v
                                                                update_memory
```

**Steps:**

1. **check_memory**: `MemoryCheckAction` checks compaction needs, sets `next_route`
2. **compact_short_term**: Subworkflow for short-term memory compaction
3. **compact_long_term**: Subworkflow for long-term memory compaction
4. **select_workflow**: `WorkflowSelectorAction` uses LLM to pick best workflow
5. **create_workflow**: `WorkflowCreatorAction` creates new workflow if needed
6. **execute_workflow**: `ExecuteGoalWorkflowAction` runs the goal workflow
7. **record_metrics**: `RecordMetricsAction` saves run to metrics store
8. **update_memory**: `UpdateMemoryAction` adds entry to agent memory

### Task Actions for Agent Loop

These actions (in `zebra-tasks/zebra_tasks/agent/`) power the agent loop:

| Action | File | Purpose |
|--------|------|---------|
| `memory_check` | `memory_check.py` | Check memory compaction needs, set routing |
| `workflow_selector` | `selector.py` | LLM-powered workflow selection |
| `workflow_creator` | `creator.py` | LLM-powered workflow creation |
| `execute_goal_workflow` | `execute_workflow.py` | Execute workflow by name |
| `record_metrics` | `record_metrics.py` | Record run to metrics store |
| `update_memory` | `update_memory.py` | Add entry to memory store |

### IoC (Inversion of Control) for Stores

Stores are passed to task actions via process properties (not constructor injection):

```python
properties = {
    "goal": goal,
    "run_id": run_id,
    "__memory_store__": self.memory,      # MemoryStore interface
    "__metrics_store__": self.metrics,     # MetricsStore interface
    "__workflow_library__": self.library,  # WorkflowLibrary instance
}
```

Actions retrieve stores from `context.process.properties`:

```python
async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
    memory_store = context.process.properties.get("__memory_store__")
    if memory_store is None:
        return TaskResult.ok(output={"added": False})  # Graceful degradation
    # Use store...
```

### Key Components

**AgentLoop** (`loop.py`):
- Thin wrapper that runs the "Agent Main Loop" workflow
- Prepares initial properties with stores and goal
- Waits for workflow completion and extracts results
- ~200 lines (down from ~700 lines in imperative version)

**WorkflowLibrary** (`library.py`):
- Manages the collection of available workflows
- Loads workflows from YAML files
- Provides search/matching capabilities
- Tracks usage metrics per workflow

**MetricsStore** (`storage/interfaces.py`):
- Abstract interface for workflow metrics storage
- Records workflow runs and task executions
- Tracks user ratings (1-5 scale)
- Calculates success rates for workflow selection

**MemoryStore** (`storage/interfaces.py`):
- Abstract interface for agent memory storage
- Two-tier memory: short-term entries + long-term themes
- Automatic compaction when thresholds exceeded

### IoC (Inversion of Control) Module

The `ioc/` module provides dependency injection and automatic task discovery, sitting on
top of `zebra-py`'s `ActionRegistry` without modifying the core engine.

**ZebraContainer** (`ioc/container.py`):
- Wraps `dependency-injector`'s `DeclarativeContainer`
- Registers services by name: `container.register_service("llm_provider", my_provider)`
- Provides typed retrieval: `container.get_service("llm_provider")`
- Includes built-in `config` and `store` providers

**IoCActionRegistry** (`ioc/registry.py`):
- Extends `ActionRegistry` with constructor injection
- Overrides `get_action()` to inspect `__init__` signatures and resolve dependencies from the container
- `discover_and_register()` loads built-in defaults + entry point discoveries
- Priority order: pre-existing registrations > built-in defaults > entry points

**Discovery** (`ioc/discovery.py`):
- `discover_actions()` scans the `zebra.tasks` entry point group
- `discover_conditions()` scans the `zebra.conditions` entry point group
- Handles Python 3.11 vs 3.12+ `importlib.metadata` API differences

**Usage:**

```python
from zebra_agent.ioc import ZebraContainer, IoCActionRegistry

container = ZebraContainer()
container.register_service("llm_provider", my_llm_provider)

registry = IoCActionRegistry(container)
registry.discover_and_register()  # loads defaults + entry points

engine = WorkflowEngine(store, registry)
```

**Entry Points** (defined in `zebra-tasks/pyproject.toml`):

All 21 task actions in `zebra-tasks` are registered as `zebra.tasks` entry points,
enabling automatic discovery without manual `register_action()` calls.

## Common Tasks

### System Workflows

These workflows are internal to the agent and excluded from LLM selection:

| Workflow | File | Purpose |
|----------|------|---------|
| `Agent Main Loop` | `agent_main_loop.yaml` | Main orchestration workflow |
| `Memory Compact Short` | `memory_compact_short.yaml` | Short-term memory compaction |
| `Memory Compact Long` | `memory_compact_long.yaml` | Long-term memory compaction |

System workflows are identified by name in `loop.py`:

```python
def _is_system_workflow(self, name: str) -> bool:
    system_workflows = {
        "Agent Main Loop",
        "Memory Compact Short", 
        "Memory Compact Long",
    }
    return name in system_workflows
```

### Add a New Built-in Workflow

1. Create YAML file in `workflows/` directory
2. Follow the workflow definition format (see `zebra-py/README.md`)
3. Add descriptive `name`, `description`, and `use_when` for LLM selection
4. Add `tags` for categorization

**Example:**

```yaml
# workflows/code_review.yaml
name: "Code Review"
version: 1
description: "Review code changes and provide feedback"
tags: ["code", "review", "development"]
use_when: "User wants code reviewed, analyzed for bugs, or feedback on implementation"

tasks:
  get_code:
    name: "Get Code to Review"
    action: prompt
    auto: false
    properties:
      prompt: "Paste the code you want reviewed:"

  analyze:
    name: "Analyze Code"
    action: llm_call
    properties:
      system_prompt: "You are an expert code reviewer."
      prompt: |
        Review this code for:
        - Bugs and errors
        - Code style issues
        - Performance concerns
        - Security vulnerabilities

        Code:
        {{get_code.output}}
      output_key: review

  present_review:
    name: "Present Review"
    action: prompt
    auto: false
    properties:
      prompt: "{{review}}"

routings:
  - from: get_code
    to: analyze
  - from: analyze
    to: present_review
```

**Key metadata fields for LLM selection:**
- `name`: Human-readable workflow name
- `description`: Brief description of what the workflow does
- `use_when`: Detailed hint for when this workflow should be selected
- `tags`: Categories for grouping similar workflows

### Modify the Agent Loop Flow

The agent loop is defined in `workflows/agent_main_loop.yaml`. To modify the flow:

1. Edit the YAML workflow definition
2. Add/remove/reorder tasks
3. Update routings for conditional flow

**Example: Adding a pre-execution validation step:**

```yaml
tasks:
  # ... existing tasks ...
  
  validate_workflow:
    name: "Validate Selected Workflow"
    action: my_validation_action
    auto: true
    properties:
      workflow_name: "{{workflow_name}}"
      goal: "{{goal}}"

routings:
  # Route from selection to validation before execution
  - from: select_workflow
    to: validate_workflow
    condition: route_name
    name: "use_existing"
  
  - from: validate_workflow
    to: execute_workflow
```

### Add a New Agent Loop Action

To add a new task action for the agent loop:

1. Create action in `zebra-tasks/zebra_tasks/agent/`
2. Register entry point in `zebra-tasks/pyproject.toml`
3. Use the action in `agent_main_loop.yaml`

**Example action with store access:**

```python
from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, TaskAction

class MyAgentAction(TaskAction):
    """Custom agent loop action."""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        # Get stores from process properties (IoC pattern)
        memory_store = context.process.properties.get("__memory_store__")
        metrics_store = context.process.properties.get("__metrics_store__")
        library = context.process.properties.get("__workflow_library__")
        
        # Graceful degradation if store not available
        if memory_store is None:
            return TaskResult.ok(output={"skipped": True})
        
        # Do work...
        result = await self._do_work(memory_store)
        
        # Set routing for conditional flow
        return TaskResult.ok(output=result, next_route="success")
```

### Add New Metrics

Extend the `MetricsStore` interface in `storage/interfaces.py`:

```python
class MetricsStore(ABC):
    # ... existing methods ...
    
    @abstractmethod
    async def record_custom_metric(self, run_id: str, metric_name: str, value: Any) -> None:
        """Record a custom metric for a run."""
        ...
```

Then implement in `InMemoryMetricsStore` and `DjangoMetricsStore`.

## CLI Commands

| Command | Description |
|---------|-------------|
| `/list` | Show available workflows |
| `/stats` | Show workflow statistics |
| `/help` | Show help |
| `/quit` | Exit |

## Testing

### Test Structure

```python
import pytest
from zebra_agent.loop import AgentLoop
from zebra_agent.library import WorkflowLibrary

@pytest.fixture
def library(tmp_path):
    """Create a test workflow library."""
    return WorkflowLibrary(tmp_path / "workflows")

@pytest.fixture
def agent(library, mock_llm_provider):
    """Create an agent for testing."""
    return AgentLoop(library=library, llm_provider=mock_llm_provider)

async def test_workflow_selection(agent):
    goal = "Help me write a function"
    workflow = await agent.select_workflow(goal)
    assert workflow is not None
```

### Mocking the LLM

```python
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def mock_llm_provider():
    provider = MagicMock()
    provider.complete = AsyncMock(return_value=LLMResponse(
        content='{"selected_workflow": "code_helper"}',
        model="test-model",
        usage={},
    ))
    return provider
```

## Related Documentation

- **[README.md](README.md)** - Package overview and usage
- **[../zebra-py/AGENTS.md](../zebra-py/AGENTS.md)** - Core engine documentation
- **[../zebra-tasks/AGENTS.md](../zebra-tasks/AGENTS.md)** - Task actions documentation
