# zebra-tasks

Reusable task actions for the [Zebra](../zebra-py) workflow engine.

## Installation

```bash
pip install zebra-tasks

# With Anthropic support
pip install zebra-tasks[anthropic]

# With OpenAI support
pip install zebra-tasks[openai]

# With all providers
pip install zebra-tasks[all]
```

## Features

### Subtask Actions

Spawn and manage sub-workflows from within a workflow:

```yaml
tasks:
  run_analysis:
    name: "Run Analysis"
    action: subworkflow
    properties:
      workflow_file: "workflows/analysis.yaml"
      properties:
        input_data: "{{data}}"
      output_key: analysis_result

  run_parallel:
    name: "Run Parallel Tasks"
    action: parallel_subworkflows
    properties:
      workflows:
        - workflow_file: "task1.yaml"
          key: result1
        - workflow_file: "task2.yaml"
          key: result2
      output_key: parallel_results
```

Available actions:
- `SubworkflowAction` - Spawn and optionally wait for a sub-workflow
- `WaitForSubworkflowAction` - Wait for a previously spawned sub-workflow
- `ParallelSubworkflowsAction` - Spawn multiple sub-workflows in parallel

### LLM Actions

Call LLM providers from workflows:

```yaml
tasks:
  analyze:
    name: "Analyze Text"
    action: llm_call
    properties:
      system_prompt: "You are a helpful analyst."
      prompt: "Analyze this text: {{input_text}}"
      temperature: 0.3
      output_key: analysis

  classify:
    name: "Classify Result"
    action: llm_call
    properties:
      prompt: |
        Based on: {{analysis}}
        Classify sentiment as JSON: {"sentiment": "...", "confidence": 0.0-1.0}
      response_format: json
      output_key: classification
```

Supported providers:
- Anthropic (Claude)
- OpenAI (GPT-4, etc.)

## Usage

### Registering Actions

```python
from zebra.tasks.registry import ActionRegistry
from zebra_tasks import SubworkflowAction, LLMCallAction

registry = ActionRegistry()
registry.register_action("subworkflow", SubworkflowAction)
registry.register_action("llm_call", LLMCallAction)
```

### Using LLM Provider

```python
from zebra_tasks.llm import get_provider

# Get provider (requires API key in environment)
provider = get_provider("anthropic", model="claude-sonnet-4-20250514")

# Use in workflow via process properties
process_properties = {
    "__llm_provider__": provider,
}
```

### Custom Provider

```python
from zebra_tasks.llm import LLMProvider, register_provider

class MyProvider(LLMProvider):
    # Implement abstract methods
    ...

register_provider("my_provider", lambda model: MyProvider(model))
```

## API Reference

### Subtask Actions

#### SubworkflowAction

Properties:
- `workflow`: Inline workflow dict, YAML string, or definition ID
- `workflow_file`: Path to workflow YAML file
- `properties`: Properties to pass to sub-workflow
- `wait`: Whether to wait for completion (default: True)
- `timeout`: Timeout in seconds (optional)
- `output_key`: Where to store result (default: "subworkflow_result")

#### ParallelSubworkflowsAction

Properties:
- `workflows`: List of workflow configs with `workflow`/`workflow_file`, `properties`, `key`
- `timeout`: Timeout for all workflows (optional)
- `fail_fast`: Stop all on first failure (default: False)
- `output_key`: Where to store results dict (default: "parallel_results")

### LLM Actions

#### LLMCallAction

Properties:
- `prompt`: User prompt (supports {{var}} templates)
- `system_prompt`: System prompt (optional)
- `messages`: Full message history (alternative to prompt/system_prompt)
- `temperature`: LLM temperature (default: 0.7)
- `max_tokens`: Maximum response tokens (default: 2000)
- `response_format`: "text" or "json" (default: "text")
- `output_key`: Where to store response (default: "llm_response")
- `provider`: Provider name override
- `model`: Model name override

## License

MIT
