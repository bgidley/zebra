# zebra-tasks Development Guide

## Overview

`zebra-tasks` is a library of reusable task actions for the Zebra workflow engine. It provides:
- **Subtask actions**: Spawn and manage sub-workflows
- **LLM actions**: Provider-agnostic LLM calling

## Project Structure

```
zebra-tasks/
├── zebra_tasks/
│   ├── subtasks/           # Sub-workflow actions
│   │   ├── spawn.py        # SubworkflowAction
│   │   ├── wait.py         # WaitForSubworkflowAction
│   │   └── parallel.py     # ParallelSubworkflowsAction
│   └── llm/                # LLM calling
│       ├── base.py         # LLMProvider interface
│       ├── action.py       # LLMCallAction
│       └── providers/      # Provider implementations
│           ├── anthropic.py
│           └── openai.py
└── tests/
```

## Running Tests

```bash
cd zebra-tasks
pip install -e ".[dev]"
pytest
```

## Key Patterns

### TaskAction Pattern

All actions extend `zebra.tasks.base.TaskAction`:

```python
class MyAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        # Access task properties
        value = task.properties.get("key")

        # Resolve templates
        resolved = context.resolve_template("{{var}}")

        # Set process properties
        context.set_process_property("output", result)

        # Return result
        return TaskResult.ok(output=result)
```

### LLM Provider Pattern

Providers implement `LLMProvider`:

```python
class MyProvider(LLMProvider):
    async def complete(self, messages, **kwargs) -> LLMResponse:
        ...

    async def stream(self, messages, **kwargs) -> AsyncIterator[str]:
        ...
```

## Dependencies

- `zebra`: Core workflow engine
- `pydantic`: Data validation
- `httpx`: HTTP client
- Optional: `anthropic`, `openai`
