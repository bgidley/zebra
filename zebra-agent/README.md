# Zebra Agent

Self-improving agent console that uses zebra workflows to achieve goals.

## Features

- **Workflow Selection**: LLM-powered selection of the best workflow for your goal
- **Workflow Creation**: Automatically creates new workflows when no match exists
- **Performance Tracking**: Tracks success rates and user ratings for continuous improvement
- **Expanding Library**: Each interaction can expand the workflow library

## Installation

```bash
# From the zebra workspace root
uv pip install -e zebra-agent
```

## Usage

```bash
# Start the interactive console
zebra-agent

# Or run directly
python -m zebra_agent.cli
```

## Commands

- `/list` - Show available workflows
- `/stats` - Show workflow statistics
- `/help` - Show help
- `/quit` - Exit

## Example

```
> What is the capital of France?

  [Using workflow: Answer Question]

  The capital of France is Paris.

  Rate this result (1-5, or Enter to skip): 5
  Thanks for the feedback!

> Brainstorm ideas for a birthday party

  [Using workflow: Brainstorm Ideas]

  ...
```

## How It Works

1. **Goal Input**: You provide a goal or question
2. **Workflow Selection**: The agent uses an LLM to select the best matching workflow
3. **Workflow Creation**: If no good match, a new workflow is created
4. **Execution**: The workflow runs through the zebra engine
5. **Rating**: You can rate the result to improve future selection

## Configuration

Data is stored in `~/.zebra-agent/`:
- `workflows/` - Workflow YAML definitions
- `state.db` - Workflow execution state
- `metrics.db` - Performance metrics
