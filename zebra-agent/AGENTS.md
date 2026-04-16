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
| `zebra_agent/budget.py` | BudgetManager — daily budget with linear pacing |
| `zebra_agent/scheduler.py` | GoalScheduler — priority + deadline + age scoring |
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
consult_memory --> select_workflow
                       |
             +---------+---------+
             |         |         |
        create_new  create_variant  use_existing
             |         |         |
             +---------+---------+
                       |
                execute_workflow
                       |
                assess_and_record
                       |
             update_conceptual_memory
```

**Steps:**

1. **consult_memory**: `ConsultMemoryAction` reads conceptual memory to produce a workflow shortlist
2. **select_workflow**: `WorkflowSelectorAction` uses LLM to pick best workflow (informed by memory shortlist)
3. **create_workflow**: `WorkflowCreatorAction` creates new workflow if no match (route: `create_new`)
4. **create_variant**: `WorkflowVariantCreatorAction` modifies existing workflow (route: `create_variant`)
5. **execute_workflow**: `ExecuteGoalWorkflowAction` runs the selected/created workflow
6. **assess_and_record**: `AssessAndRecordAction` records metrics + LLM effectiveness assessment + workflow memory entry
7. **update_conceptual_memory**: `UpdateConceptualMemoryAction` incrementally updates the conceptual memory index

### Task Actions for Agent Loop

These actions (in `zebra-tasks/zebra_tasks/agent/`) power the agent loop:

| Action | File | Purpose |
|--------|------|---------|
| `consult_memory` | `consult_memory.py` | Read conceptual memory for workflow shortlist |
| `workflow_selector` | `selector.py` | LLM-powered workflow selection |
| `workflow_creator` | `creator.py` | LLM-powered workflow creation |
| `workflow_variant_creator` | `variant_creator.py` | LLM-powered workflow variant creation |
| `execute_goal_workflow` | `execute_workflow.py` | Execute workflow by name |
| `assess_and_record` | `assess_and_record.py` | LLM assessment + metrics + memory write |
| `update_conceptual_memory` | `update_conceptual_memory.py` | Incrementally update conceptual memory index |

These actions power the Dream Cycle self-improvement workflow:

| Action | File | Purpose |
|--------|------|---------|
| `metrics_analyzer` | `analyzer.py` | Analyze metrics via MetricsStore interface |
| `load_workflow_definitions` | `load_definitions.py` | Load workflow YAML via WorkflowLibrary |
| `workflow_evaluator` | `evaluator.py` | LLM-based evaluation of workflow effectiveness |
| `workflow_optimizer` | `optimizer.py` | Create/optimize workflows based on evaluation |

### IoC (Inversion of Control) for Stores

Stores are passed to task actions via `engine.extras` (engine-level dependency injection), not process properties:

```python
# In AgentLoop.__init__(), stores are injected into engine.extras
self.engine.extras["__memory_store__"] = memory
self.engine.extras["__metrics_store__"] = metrics
self.engine.extras["__workflow_library__"] = library
```

This approach keeps non-serializable objects out of process properties (which must be JSON-serializable for persistence).

Actions retrieve stores from `context.extras`:

```python
async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
    memory_store = context.extras.get("__memory_store__")
    if memory_store is None:
        return TaskResult.ok(output={"added": False})  # Graceful degradation
    # Use store...
```

**Note:** Previous versions used `context.process.properties` for store injection, but this violated the JSON-serialization requirement for process properties.

### Storage Abstraction Design Rules

All task actions that read or write agent data **must** use the abstract store
interfaces (`MemoryStore`, `MetricsStore`) from `context.extras`, never direct
database access or raw file I/O.

**Why**: `zebra-agent` supports multiple storage backends — `InMemoryMemoryStore`
for CLI/testing, `DjangoMemoryStore` / `DjangoMetricsStore` for the web app
(Oracle, PostgreSQL, etc.). Task actions must work identically regardless of
the backend. Coupling to a specific driver (e.g. `aiosqlite`, `psycopg2`)
breaks portability across deployments.

**Rules:**

1. **Never import a database driver** (e.g. `aiosqlite`, `psycopg2`) in a task
   action. All data access goes through the injected store interfaces.

2. **Never read workflow files from disk directly.** Use `WorkflowLibrary` from
   `context.extras["__workflow_library__"]`, which handles caching, versioning,
   and path resolution.

3. **Always degrade gracefully** when a store is `None` — return a sensible
   default rather than failing. This supports standalone use without a database.

4. **New interface methods** must be added to the ABC in
   `storage/interfaces.py` first, then implemented in *all* backends
   (`InMemoryMetricsStore`, `DjangoMetricsStore`, and any future backends).
   A downstream storage implementation must never be required to work around
   a missing interface method.

5. **Test with mocks**, not real databases. Mock the store interface in unit
   tests (see `zebra-tasks/tests/test_agent_loop_actions.py` for examples).

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

**BudgetManager** (`budget.py`):
- Tracks daily LLM spend against a configurable dollar budget
- Linear pacing: `allowed_at_time = daily_budget * (elapsed / 24h)`
- `can_start_goal(estimated_cost)` checks remaining budget
- `warn_if_over(goal_id, cost_so_far)` logs soft warning if per-goal threshold exceeded
- Stateless: calculates "spent today" by querying `MetricsStore.get_total_cost_since()`

**GoalScheduler** (`scheduler.py`):
- Picks the next goal to execute from CREATED processes
- Scoring formula: `priority_score + deadline_boost + age_bonus`
- Priority 1-5 mapped to scores (1=highest gets highest score)
- Approaching deadlines exponentially boost effective priority
- Age-based anti-starvation prevents low-priority goals from waiting forever

**MemoryStore** (`storage/interfaces.py`):
- Abstract interface for agent memory storage
- Two-tier memory: workflow memory (detailed per-run records) + conceptual memory (compact goal-pattern index)
- Conceptual memory is consulted at the start of each goal for workflow shortlisting
- Updated incrementally after each run via LLM classification

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
| `Dream Cycle` | `dream_cycle.yaml` | Self-improvement: analyze, evaluate, optimize workflows |
| `Create Goal` | `create_goal.yaml` | Human input → queue goal as CREATED process |

System workflows are identified by name in `loop.py`:

```python
def _is_system_workflow(self, name: str) -> bool:
    system_workflows = {
        "Agent Main Loop",
        "Dream Cycle",
        "Create Goal",
    }
    return name in system_workflows
```

The Dream Cycle can be triggered explicitly via:
- `AgentLoop.run_dream_cycle()` in Python
- `python manage.py dream_cycle` in Django (zebra-agent-web)
- `POST /api/dream-cycle/` API endpoint (zebra-agent-web)

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
        # Get stores from context.extras (engine-level IoC pattern)
        memory_store = context.extras.get("__memory_store__")
        metrics_store = context.extras.get("__metrics_store__")
        library = context.extras.get("__workflow_library__")
        
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
