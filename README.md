# Zebra Workflow Engine

A workflow engine for AI-assisted development tasks. Zebra enables structured execution of complex, long-running workflows with support for parallel execution, conditional routing, and LLM integration.

## Project Structure

```
zebra/
├── zebra-py/          # Python workflow engine (primary implementation)
├── zebra-rs/          # Rust workflow engine (alternative implementation)
├── zebra-tasks/       # Reusable task actions library (Python)
├── zebra-agents/      # Self-improving AI agent framework (in development)
└── legacy/            # Legacy Java implementation (archived)
```

### Components

| Package | Language | Description |
|---------|----------|-------------|
| **zebra-py** | Python | Core workflow engine with MCP server integration |
| **zebra-rs** | Rust | High-performance workflow engine implementation |
| **zebra-tasks** | Python | Reusable task actions (subtasks, LLM calling) |
| **zebra-agents** | Python | Autonomous agent framework built on zebra workflows |

## Quick Start

### Python (zebra-py)

```bash
cd zebra-py
uv sync
uv run python -c "from zebra import WorkflowEngine; print('Ready!')"
```

### Rust (zebra-rs)

```bash
cd zebra-rs
cargo build
cargo run
```

## Building

### Python Packages

All Python packages use [uv](https://github.com/astral-sh/uv) for dependency management.

```bash
# zebra-py (core engine)
cd zebra-py
uv sync --extra dev --extra mcp

# zebra-tasks (task library)
cd zebra-tasks
uv sync --extra dev --extra all
```

### Rust Package

```bash
cd zebra-rs
cargo build --release
```

## Running Tests

### Python

```bash
# zebra-py tests
cd zebra-py
uv run pytest tests/ -v

# zebra-tasks tests
cd zebra-tasks
uv run pytest tests/ -v
```

### Rust

```bash
cd zebra-rs
cargo test
```

### Run All Tests

```bash
# From project root
cd zebra-py && uv run pytest tests/ -v && cd ..
cd zebra-tasks && uv run pytest tests/ -v && cd ..
cd zebra-rs && cargo test && cd ..
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
- [zebra-rs workflows](zebra-rs/workflows.md) - Rust workflow patterns
- [Design Document](design.md) - Original design specification

## License

Apache License 2.0 (see [LICENSE.txt](LICENSE.txt))

## Credits

Based on the Java Zebra workflow engine originally developed by Anite (2004) and modified by Ben Gidley (2010).
