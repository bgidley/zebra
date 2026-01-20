# Zebra Workflow Engine

A workflow engine for AI-assisted development tasks. Zebra enables structured execution of complex, long-running workflows with support for parallel execution, conditional routing, and LLM integration.

## Project Structure

```
zebra/
├── zebra-py/          # Python workflow engine (primary implementation)
├── zebra-tasks/       # Reusable task actions library (Python)
├── zebra-agents/      # Self-improving AI agent framework (in development)
└── legacy/            # Legacy Java implementation (archived)
```

### Components

| Package | Language | Description |
|---------|----------|-------------|
| **zebra-py** | Python | Core workflow engine with MCP server integration |
| **zebra-tasks** | Python | Reusable task actions (subtasks, LLM calling) |
| **zebra-agents** | Python | Autonomous agent framework built on zebra workflows |

## Quick Start

### Python (zebra-py)

```bash
cd zebra-py
uv sync
uv run python -c "from zebra import WorkflowEngine; print('Ready!')"
```

## Building

This project uses [uv workspaces](https://docs.astral.sh/uv/concepts/workspaces/) to manage multiple Python packages.

### All Python Packages (Recommended)

```bash
# From project root - syncs all packages
uv sync --all-packages
```

### Individual Packages

```bash
# zebra-py only
cd zebra-py && uv sync

# zebra-tasks only
cd zebra-tasks && uv sync
```

## Running Tests

### All Python Tests (Recommended)

```bash
# From project root - runs all Python tests
uv run pytest
```

### Individual Package Tests

```bash
# zebra-py tests only
uv run pytest zebra-py/tests/ -v

# zebra-tasks tests only
uv run pytest zebra-tasks/tests/ -v
```


### All Tests (Python + Rust)

```bash
uv run pytest && cd zebra-rs && cargo test
```

## Running the MCP Server

The MCP server enables Claude and other AI tools to create and manage workflows.

```bash
cd zebra-py
uv run python -m zebra.mcp.server
```

Configure in Claude Code settings:

```json
{
  "mcpServers": {
    "zebra-workflow": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/zebra-py", "python", "-m", "zebra.mcp.server"]
    }
  }
}
```

## Example Workflow

```yaml
name: "Code Review"
version: 1

tasks:
  analyze:
    name: "Analyze Code"
    action: llm_call
    properties:
      prompt: "Analyze this code for issues: {{code}}"
      output_key: analysis

  review:
    name: "Review"
    action: prompt
    auto: false
    properties:
      prompt: "Review analysis: {{analysis}}"

routings:
  - from: analyze
    to: review
```

## Documentation

- [zebra-py README](zebra-py/README.md) - Full Python engine documentation
- [zebra-tasks README](zebra-tasks/README.md) - Task actions documentation
- [Design Document](design.md) - Original design specification

## License

Apache License 2.0 (see [LICENSE.txt](LICENSE.txt))

## Credits

Based on the Java Zebra workflow engine originally developed by Anite (2004) and modified by Ben Gidley (2010).
