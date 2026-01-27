# AGENTS.md - zebra-agent-cli

This package provides the interactive CLI for the Zebra Agent. It's a thin wrapper around the `zebra-agent` library.

## Package Structure

```
zebra-agent-cli/
├── zebra_agent_cli/
│   ├── __init__.py
│   └── main.py          # CLI implementation
├── tests/
│   ├── conftest.py      # Test fixtures
│   └── test_main.py     # CLI tests
├── pyproject.toml
├── README.md
└── AGENTS.md
```

## Key Files

- **`main.py`**: Contains the CLI implementation including:
  - `run()` - Entry point
  - `async_main()` - Main async loop
  - `cmd_list()`, `cmd_stats()`, `cmd_memory()`, `cmd_help()` - Command handlers
  - `cmd_dream()` - Self-improvement cycle
  - `print_banner()` - Welcome banner

## Dependencies

This package depends on:
- `zebra-agent` - Core library (AgentLoop, WorkflowLibrary, etc.)
- `zebra-workflow` - Workflow engine
- `zebra-tasks[anthropic]` - LLM actions

## Testing

```bash
# Run CLI tests
uv run pytest zebra-agent-cli/tests/ -v
```

## Guidelines

1. **Keep CLI thin** - Business logic belongs in `zebra-agent` library
2. **Test commands** - Each command should have test coverage
3. **Mock dependencies** - Tests should mock PostgreSQL and LLM providers

## Related Documentation

- See [zebra-agent/AGENTS.md](../zebra-agent/AGENTS.md) for library guidelines
- See [../AGENTS.md](../AGENTS.md) for workspace guidelines
