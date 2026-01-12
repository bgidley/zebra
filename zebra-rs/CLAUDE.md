# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Zebra is a workflow engine with implementations in multiple languages:
- **zebra-rs/** - Modern Rust port (async/await with Tokio)
- **zebra-py/** - Modern Python port (async with SQLite persistence, MCP integration)
- **Root Java modules** - Legacy 2004 codebase (Maven multi-module)

Current development is on the `python-modernization` branch. The `master` branch contains stable Java/legacy code.

## Build and Test Commands

### Rust (zebra-rs)

```bash
cd zebra-rs

# Build
cargo build                          # Debug build
cargo build --release               # Release build

# Test
cargo test                          # All tests
cargo test --test test_engine       # Specific test file
cargo test test_name                # Single test by name
cargo test --release perf_          # Performance tests (release mode)

# Lint and format
cargo clippy                        # Linting
cargo fmt --check                   # Check formatting
cargo fmt                           # Auto-format
```

### Python (zebra-py)

```bash
cd zebra-py

# Setup
uv sync                             # Install dependencies

# Test
uv run python -m pytest tests/ -v                    # All tests
uv run python -m pytest tests/test_engine.py -v     # Specific file
uv run python -m pytest tests/ -k "test_name" -v    # Single test
uv run python -m pytest tests/test_performance.py -v # Performance tests

# Lint
uv run ruff check .                 # Check style
uv run ruff check --fix .           # Auto-fix

# MCP Server
uv run python -m zebra.mcp.server   # Run MCP server for Claude
```

### Java (Legacy)

```bash
mvn clean compile                   # Compile
mvn test                            # Run tests
```

## Architecture

The workflow engine follows a layered, interface-driven architecture:

```
Workflow Definitions (YAML/JSON)
         ↓
   Definition Loaders
         ↓
   WorkflowEngine (Core)
    ├── Process lifecycle (create → start → complete)
    ├── Task state transitions (ready → running → complete)
    ├── Routing evaluation (serial vs parallel)
    └── Synchronization/join handling
         ↓
    ┌────┴────┐
    ↓         ↓
TaskActions  StateStore
(pluggable)  (SQLite/Memory)
```

### Core Components

| Component | Python | Rust |
|-----------|--------|------|
| Engine | `zebra/core/engine.py` | `src/core/engine.rs` |
| Models | `zebra/core/models.py` | `src/core/models.rs` |
| Storage | `zebra/storage/` | `src/storage/` |
| Actions | `zebra/tasks/` | `src/tasks/` |
| Loader | `zebra/definitions/loader.py` | `src/definitions/` |

### Key Concepts

**Process/Task States:**
- ProcessState: `created → running → complete` (optionally `paused`)
- TaskState: `pending → awaiting_sync → ready → running → complete`

**Flow of Execution (FOE):** Tracks parallel execution branches. Serial routings inherit parent FOE; parallel routings create new FOEs. Synchronized tasks wait for all incoming FOEs.

**TaskAction Interface:** Custom actions implement `async run(task, context) -> TaskResult`. Register in `ActionRegistry` by name.

**StateStore Interface:** Abstracts persistence. Implementations: `InMemoryStore` (testing), `SQLiteStore` (production).

## Extension Points

1. **Custom TaskActions** - Implement `TaskAction` base class, register with `ActionRegistry`
2. **Custom ConditionActions** - Implement `ConditionAction` for routing conditions
3. **Storage backends** - Implement `StateStore` trait/ABC

## Related Documentation

- `design.md` - Original Java architecture and design patterns
- `zebra-py/README.md` - Python usage guide and YAML definition reference
- `zebra-py/workflows.md` - Workflow Control-Flow Patterns (43 patterns mapped)
