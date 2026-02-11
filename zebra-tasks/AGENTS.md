# AGENTS.md - zebra-tasks (Task Actions Library)

This file provides coding agent guidelines specific to the `zebra-tasks` package - reusable task actions for the Zebra workflow engine.

> **Note**: For project-wide guidelines (code style, testing patterns, important rules), see the [root AGENTS.md](../AGENTS.md).

## Package Overview

`zebra-tasks` provides reusable task actions that extend the core workflow engine:
- **LLM Actions**: Call LLM providers (Anthropic, OpenAI) from workflows
- **Subtask Actions**: Spawn and manage sub-workflows
- **Compute Actions**: Computational task utilities
- **Agent Actions**: Agent-specific task actions

## File Locations

| Directory | Purpose |
|-----------|---------|
| `zebra_tasks/` | Package root |
| `zebra_tasks/llm/` | LLM provider integrations |
| `zebra_tasks/llm/base.py` | LLMProvider base class, Message model |
| `zebra_tasks/llm/action.py` | LLMCallAction task action |
| `zebra_tasks/llm/providers/` | Provider implementations |
| `zebra_tasks/llm/providers/anthropic.py` | Anthropic (Claude) provider |
| `zebra_tasks/llm/providers/openai.py` | OpenAI provider |
| `zebra_tasks/subtasks/` | Sub-workflow actions |
| `zebra_tasks/subtasks/subworkflow.py` | SubworkflowAction, ParallelSubworkflowsAction |
| `zebra_tasks/compute/` | Computational utilities |
| `zebra_tasks/agent/` | Agent-specific actions |
| `zebra_tasks/agent/selector.py` | WorkflowSelectorAction - LLM workflow selection |
| `zebra_tasks/agent/creator.py` | WorkflowCreatorAction - LLM workflow creation |
| `zebra_tasks/agent/memory_check.py` | MemoryCheckAction - memory compaction check |
| `zebra_tasks/agent/execute_workflow.py` | ExecuteGoalWorkflowAction - run workflow by name |
| `zebra_tasks/agent/record_metrics.py` | RecordMetricsAction - record run to metrics |
| `zebra_tasks/agent/update_memory.py` | UpdateMemoryAction - add memory entry |
| `zebra_tasks/agent/analyzer.py` | MetricsAnalyzerAction - analyze workflow metrics |
| `zebra_tasks/agent/evaluator.py` | WorkflowEvaluatorAction - LLM workflow evaluation |
| `zebra_tasks/agent/optimizer.py` | WorkflowOptimizerAction - LLM workflow optimization |
| `tests/` | Test suite |

## Module-Specific Commands

```bash
# Run tests for this package only
uv run pytest zebra-tasks/tests/ -v

# Run single test file
uv run pytest zebra-tasks/tests/test_llm.py -v

# Run tests matching pattern
uv run pytest zebra-tasks/tests/ -k "subworkflow" -v
```

## Common Tasks

### Add a New Task Action

1. Create a new module in the appropriate subdirectory (`llm/`, `subtasks/`, `compute/`, `agent/`)
2. Inherit from `TaskAction` (from `zebra.tasks.base`)
3. Implement `async def run(task, context) -> TaskResult`
4. Export from package `__init__.py`
5. Add tests in `tests/`

**Example:**

```python
from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, TaskAction

class MyNewAction(TaskAction):
    """Description of what this action does."""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        # Get task properties
        input_value = task.properties.get("input_key")
        
        # Resolve templates
        resolved = context.resolve_template("{{some_var}}")
        
        # Do the work
        result = await self._do_work(input_value, resolved)
        
        # Store output in process properties
        output_key = task.properties.get("output_key", "default_output")
        context.set_process_property(output_key, result)
        
        return TaskResult.ok(output={"result": result})
    
    async def _do_work(self, input_value: str, resolved: str) -> str:
        # Implementation
        ...
```

### Add a New LLM Provider

1. Create provider class in `zebra_tasks/llm/providers/`
2. Inherit from `LLMProvider` base class
3. Implement required methods: `complete()`, `stream()` (if supported)
4. Register provider in `zebra_tasks/llm/__init__.py`

**Example:**

```python
from zebra_tasks.llm.base import LLMProvider, Message, LLMResponse

class MyProvider(LLMProvider):
    """My custom LLM provider."""

    def __init__(self, model: str = "default-model", api_key: str | None = None):
        super().__init__(model)
        self.api_key = api_key or os.environ.get("MY_PROVIDER_API_KEY")
        self.client = MyClient(api_key=self.api_key)

    async def complete(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs,
    ) -> LLMResponse:
        # Call provider API
        response = await self.client.chat(
            model=self.model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return LLMResponse(
            content=response.text,
            model=self.model,
            usage={"input_tokens": response.input_tokens, "output_tokens": response.output_tokens},
        )

# Register in __init__.py
register_provider("my_provider", lambda model: MyProvider(model))
```

## Task Action Reference

### LLMCallAction

Call an LLM provider from a workflow task.

**Properties:**

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `prompt` | string | - | User prompt (supports `{{var}}` templates) |
| `system_prompt` | string | null | System prompt |
| `messages` | list | null | Full message history (alternative to prompt/system_prompt) |
| `temperature` | float | 0.7 | LLM temperature |
| `max_tokens` | int | 2000 | Maximum response tokens |
| `response_format` | string | "text" | "text" or "json" |
| `output_key` | string | "llm_response" | Where to store response |
| `provider` | string | null | Provider name override |
| `model` | string | null | Model name override |

### SubworkflowAction

Spawn and optionally wait for a sub-workflow.

**Properties:**

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `workflow` | dict/string | - | Inline workflow dict, YAML string, or definition ID |
| `workflow_file` | string | - | Path to workflow YAML file |
| `properties` | dict | {} | Properties to pass to sub-workflow |
| `wait` | bool | true | Whether to wait for completion |
| `timeout` | int | null | Timeout in seconds |
| `output_key` | string | "subworkflow_result" | Where to store result |

### ParallelSubworkflowsAction

Spawn multiple sub-workflows in parallel.

**Properties:**

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `workflows` | list | - | List of workflow configs with `workflow`/`workflow_file`, `properties`, `key` |
| `timeout` | int | null | Timeout for all workflows |
| `fail_fast` | bool | false | Stop all on first failure |
| `output_key` | string | "parallel_results" | Where to store results dict |

## Agent Actions Reference

These actions power the `zebra-agent` workflow-based agent loop. They're in `zebra_tasks/agent/`.

### MemoryCheckAction

Check if agent memory needs compaction. Sets `next_route` for conditional workflow routing.

**Properties:**

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `output_key` | string | "memory_status" | Where to store check result |

**Output:**

| Field | Type | Description |
|-------|------|-------------|
| `needs_short_term` | bool | True if short-term compaction needed |
| `needs_long_term` | bool | True if long-term compaction needed |

**Routes:** `"compact_short"`, `"compact_long"`, or `"continue"`

**Store Access:** Reads `__memory_store__` from process properties.

### WorkflowSelectorAction

LLM-powered workflow selection from available workflows.

**Properties:**

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `goal` | string | - | User's goal to match |
| `available_workflows` | list | - | List of workflow metadata dicts |
| `output_key` | string | "selection" | Where to store selection result |

**Output:**

| Field | Type | Description |
|-------|------|-------------|
| `workflow_name` | string | Selected workflow name (or null) |
| `suggested_name` | string | Suggested name if creating new |
| `confidence` | float | Selection confidence (0-1) |

**Routes:** `"use_existing"` or `"create_new"`

### WorkflowCreatorAction

LLM-powered workflow creation when no match exists.

**Properties:**

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `goal` | string | - | User's goal |
| `suggested_name` | string | null | Suggested workflow name |
| `existing_workflows` | list | [] | Existing workflows for context |
| `output_key` | string | "created_workflow" | Where to store result |

**Output:**

| Field | Type | Description |
|-------|------|-------------|
| `workflow_name` | string | Created workflow name |
| `created_new` | bool | Always true |

**Side Effects:** Adds workflow to library via `__workflow_library__`.

### ExecuteGoalWorkflowAction

Execute a workflow by name and capture its output.

**Properties:**

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `workflow_name` | string | - | Name of workflow to execute |
| `goal` | string | - | Goal to pass to workflow |
| `timeout` | float | 120 | Max execution time in seconds |
| `output_key` | string | "execution_result" | Where to store result |

**Output:**

| Field | Type | Description |
|-------|------|-------------|
| `success` | bool | Whether workflow completed successfully |
| `output` | any | Workflow's output |
| `tokens_used` | int | Total tokens used |
| `error` | string | Error message if failed |

**Store Access:** Reads `__workflow_library__` from process properties.

### RecordMetricsAction

Record workflow run to metrics store.

**Properties:**

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `run_id` | string | - | Unique run identifier |
| `workflow_name` | string | - | Workflow that was executed |
| `goal` | string | - | User's original goal |
| `success` | bool | - | Whether run succeeded |
| `output` | any | null | Workflow output |
| `tokens_used` | int | 0 | Tokens used |
| `error` | string | null | Error message if failed |
| `started_at` | string | null | ISO timestamp when run started |

**Output:**

| Field | Type | Description |
|-------|------|-------------|
| `recorded` | bool | Whether metrics were recorded |

**Store Access:** Reads `__metrics_store__` from process properties. Gracefully degrades if not available.

### UpdateMemoryAction

Add memory entry for completed workflow run.

**Properties:**

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `run_id` | string | - | Unique run identifier |
| `goal` | string | - | User's original goal |
| `workflow_name` | string | - | Workflow that was used |
| `result_summary` | any | null | Summary of result (truncated to 500 chars) |

**Output:**

| Field | Type | Description |
|-------|------|-------------|
| `added` | bool | Whether memory entry was added |

**Store Access:** Reads `__memory_store__` from process properties. Gracefully degrades if not available.

## Testing Task Actions

### Test Structure

```python
import pytest
from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext
from zebra_tasks import MyAction

@pytest.fixture
def mock_context():
    """Create a mock ExecutionContext for testing."""
    # Setup mock context
    ...

async def test_my_action_success(mock_context):
    action = MyAction()
    task = TaskInstance(
        id="test-task",
        definition_id="test-def",
        process_id="test-process",
        properties={"input_key": "test value"},
    )
    
    result = await action.run(task, mock_context)
    
    assert result.success
    assert result.output["result"] == "expected"
```

### Mocking LLM Providers

```python
from unittest.mock import AsyncMock, MagicMock
from zebra_tasks.llm.base import LLMResponse

@pytest.fixture
def mock_provider():
    provider = MagicMock()
    provider.complete = AsyncMock(return_value=LLMResponse(
        content="Mocked response",
        model="test-model",
        usage={"input_tokens": 10, "output_tokens": 20},
    ))
    return provider
```

## Related Documentation

- **[README.md](README.md)** - Package overview and usage examples
- **[../zebra-py/AGENTS.md](../zebra-py/AGENTS.md)** - Core engine documentation
