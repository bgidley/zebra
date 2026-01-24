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
| `zebra_agent/metrics.py` | Performance metrics tracking |
| `workflows/` | Built-in workflow definitions |
| `tests/` | Test suite |

## Data Storage

Agent data is stored in `~/.zebra-agent/`:

| Path | Purpose |
|------|---------|
| `~/.zebra-agent/workflows/` | Workflow YAML definitions |
| `~/.zebra-agent/state.db` | Workflow execution state |
| `~/.zebra-agent/metrics.db` | Performance metrics |

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

### Agent Loop

The main agent loop follows this flow:

1. **Goal Input**: User provides a goal or question
2. **Workflow Selection**: LLM selects the best matching workflow from library
3. **Workflow Creation**: If no good match, LLM creates a new workflow
4. **Execution**: Workflow runs through the zebra engine
5. **Rating**: User can rate the result to improve future selection

### Key Components

**WorkflowLibrary** (`library.py`):
- Manages the collection of available workflows
- Loads workflows from YAML files
- Provides search/matching capabilities

**MetricsTracker** (`metrics.py`):
- Records workflow execution outcomes
- Tracks user ratings (1-5 scale)
- Calculates success rates for workflow selection

**AgentLoop** (`loop.py`):
- Orchestrates the goal → workflow → result flow
- Handles LLM interactions for selection/creation
- Manages user interaction and feedback

## Common Tasks

### Add a New Built-in Workflow

1. Create YAML file in `workflows/` directory
2. Follow the workflow definition format (see `zebra-py/README.md`)
3. Add descriptive name and metadata for LLM selection

**Example:**

```yaml
# workflows/code_review.yaml
name: "Code Review"
version: 1
description: "Review code changes and provide feedback"

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

### Modify Workflow Selection Logic

The workflow selection logic is in `loop.py`. Key areas:

```python
async def select_workflow(self, goal: str) -> WorkflowDefinition | None:
    """Select the best workflow for a goal using LLM."""
    # Get available workflows with their metadata
    workflows = self.library.list_workflows()
    
    # Build prompt for LLM selection
    # ...
    
    # Return selected workflow or None if new one needed
```

### Add New Metrics

Extend `metrics.py` to track additional data:

```python
class MetricsTracker:
    async def record_execution(
        self,
        workflow_id: str,
        goal: str,
        success: bool,
        duration_ms: int,
        rating: int | None = None,
        # Add new fields here
        custom_metric: str | None = None,
    ) -> None:
        ...
```

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
