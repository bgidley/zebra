# Zebra Workflow Engine (Python)

A modern Python workflow engine designed for AI-assisted development workflows. Zebra enables Claude and other AI systems to plan and execute complex, long-running development tasks through a structured workflow model.

## Features

- **YAML Workflow Definitions**: Human and AI-readable workflow definitions
- **Parallel Execution**: Support for parallel task branches with synchronization points
- **Pluggable Actions**: Extensible task action system for custom behaviors
- **Persistent State**: SQLite-based persistence for resumable workflows
- **MCP Integration**: Model Context Protocol server for Claude integration
- **Type Safety**: Full type hints with Pydantic models

## Installation

```bash
# Install with uv
uv add zebra-workflow

# With MCP server support
uv add zebra-workflow --extra mcp

# For development
uv sync --extra dev
```

## Quick Start

### Define a Workflow

Create a YAML workflow definition:

```yaml
# my_workflow.yaml
name: "Feature Implementation"
version: 1

tasks:
  gather_requirements:
    name: "Gather Requirements"
    action: prompt
    auto: false
    properties:
      prompt: "What feature should we implement?"

  create_plan:
    name: "Create Plan"
    action: prompt
    auto: false
    properties:
      prompt: "Create a plan for: {{gather_requirements.output}}"

  implement:
    name: "Implement"
    action: shell
    properties:
      command: "echo 'Implementing...'"

routings:
  - from: gather_requirements
    to: create_plan
  - from: create_plan
    to: implement
```

### Run the Workflow

```python
import asyncio
from zebra import WorkflowEngine
from zebra.storage import SQLiteStore
from zebra.tasks import ActionRegistry
from zebra.definitions import load_definition

async def main():
    # Initialize storage and registry
    store = SQLiteStore("workflows.db")
    await store.initialize()

    registry = ActionRegistry()
    registry.register_defaults()

    # Create engine
    engine = WorkflowEngine(store, registry)

    # Load and start workflow
    definition = load_definition("my_workflow.yaml")
    process = await engine.create_process(definition)
    await engine.start_process(process.id)

    # Handle manual tasks
    while True:
        pending = await engine.get_pending_tasks(process.id)
        if not pending:
            break

        task = pending[0]
        print(f"Task: {task.properties.get('__prompt__', 'No prompt')}")
        response = input("Your response: ")

        from zebra.core.models import TaskResult
        await engine.complete_task(task.id, TaskResult.ok(response))

    print("Workflow complete!")

asyncio.run(main())
```

Run with:

```bash
uv run python my_script.py
```

## Workflow Concepts

### Tasks

Tasks are the building blocks of workflows. Each task has:

- **id**: Unique identifier within the workflow
- **name**: Human-readable name
- **action**: Name of the TaskAction to execute
- **auto**: If True, executes automatically; if False, waits for manual completion
- **synchronized**: If True, waits for all incoming parallel branches
- **properties**: Configuration passed to the action (values must be JSON-serializable)

### Routings

Routings define the flow between tasks:

- **from/to**: Source and destination task IDs
- **parallel**: If True, creates a new execution branch
- **condition**: Optional condition to evaluate before routing

### Parallel Execution & Synchronization

Workflows can split into parallel branches and rejoin:

```yaml
tasks:
  start:
    name: Start

  task_a:
    name: Task A

  task_b:
    name: Task B

  join:
    name: Join
    synchronized: true  # Waits for both branches

routings:
  - from: start
    to: task_a
    parallel: true

  - from: start
    to: task_b
    parallel: true

  - from: task_a
    to: join

  - from: task_b
    to: join
```

## Workflow Definition Reference

Workflows are defined in YAML format with the following structure:

### Basic Structure

```yaml
name: "Workflow Name"          # Required: Human-readable name
version: 1                      # Optional: Version number (default: 1)
first_task: task_id            # Optional: Entry point (default: first defined task)

tasks:                         # Required: Map of task definitions
  task_id:
    # Task definition...

routings:                      # Optional: List of routing definitions
  - from: source_task
    to: dest_task
```

### Task Definition

Each task defines a step in the workflow:

```yaml
tasks:
  my_task:
    name: "Human Readable Name"    # Required: Display name
    action: prompt                  # Optional: Action to execute (prompt, shell, etc.)
    auto: true                      # Optional: Auto-execute (default: true)
    synchronized: false             # Optional: Wait for parallel branches (default: false)
    construct_action: action_name   # Optional: Run before task starts
    destruct_action: action_name    # Optional: Run after task completes
    properties:                     # Optional: Task-specific configuration
      key: value
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | task_id | Human-readable name |
| `action` | string | null | Action to execute (`prompt`, `shell`) |
| `auto` | bool | true | If false, waits for manual completion |
| `synchronized` | bool | false | Join point for parallel branches |
| `properties` | object | {} | Configuration passed to the action. **Values must be JSON-serializable** (strings, numbers, booleans, lists, dicts, null). |

### Routing Definition

Routings define the flow between tasks:

```yaml
routings:
  - from: source_task              # Required: Source task ID
    to: destination_task           # Required: Destination task ID
    parallel: false                # Optional: Create parallel branch (default: false)
    condition: condition_name      # Optional: Condition to evaluate
    name: "route_name"             # Optional: Name for conditional routing
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `from` | string | - | Source task ID (required) |
| `to` | string | - | Destination task ID (required) |
| `parallel` | bool | false | If true, creates a new parallel execution branch |
| `condition` | string | null | Condition action to evaluate before routing |
| `name` | string | null | Route name (used by `route_name` condition) |

### Template Variables

Task properties support template variables to reference outputs from previous tasks:

```yaml
tasks:
  first_task:
    name: "Get Input"
    action: prompt
    properties:
      prompt: "What should we do?"

  second_task:
    name: "Use Input"
    action: prompt
    properties:
      prompt: "Processing: {{first_task.output}}"  # References first_task's result
```

### Parallel Execution

Create parallel branches by using `parallel: true` on routings:

```yaml
tasks:
  start:
    name: "Start"

  branch_a:
    name: "Branch A"

  branch_b:
    name: "Branch B"

  join:
    name: "Join Point"
    synchronized: true    # Waits for ALL incoming branches

routings:
  - from: start
    to: branch_a
    parallel: true        # Creates parallel branch

  - from: start
    to: branch_b
    parallel: true        # Creates parallel branch

  - from: branch_a
    to: join

  - from: branch_b
    to: join              # join task waits for both branches
```

### Conditional Routing

Use conditions to create decision points:

```yaml
tasks:
  decision:
    name: "Make Decision"
    action: prompt
    auto: false
    properties:
      prompt: "Approve? (yes/no)"

  approved:
    name: "Approved Path"

  rejected:
    name: "Rejected Path"

routings:
  - from: decision
    to: approved
    condition: route_name
    name: "yes"           # Fires when task result's next_route is "yes"

  - from: decision
    to: rejected
    condition: route_name
    name: "no"            # Fires when task result's next_route is "no"
```

The `route_name` condition checks if the task's result `next_route` matches the routing's `name`.

### Complete Example: Feature Implementation

```yaml
name: "Feature Implementation"
version: 1
first_task: gather_requirements

tasks:
  gather_requirements:
    name: "Gather Requirements"
    action: prompt
    auto: false
    properties:
      prompt: "What feature should we implement?"

  create_plan:
    name: "Create Plan"
    action: prompt
    auto: false
    properties:
      prompt: |
        Requirements: {{gather_requirements.output}}

        Create a detailed implementation plan.

  review_plan:
    name: "Review Plan"
    action: prompt
    auto: false
    properties:
      prompt: |
        Plan: {{create_plan.output}}

        Approve this plan? (yes/modify)

  implement:
    name: "Implement"
    action: prompt
    auto: false
    properties:
      prompt: "Implement according to: {{create_plan.output}}"

  run_tests:
    name: "Run Tests"
    action: shell
    properties:
      command: "pytest tests/"

  final_review:
    name: "Final Review"
    synchronized: true
    action: prompt
    auto: false
    properties:
      prompt: |
        Implementation complete.
        Test results: {{run_tests.output}}

        Approve for merge?

routings:
  - from: gather_requirements
    to: create_plan

  - from: create_plan
    to: review_plan

  - from: review_plan
    to: implement
    condition: route_name
    name: "yes"

  - from: review_plan
    to: create_plan
    condition: route_name
    name: "modify"

  - from: implement
    to: run_tests
    parallel: true

  - from: implement
    to: final_review

  - from: run_tests
    to: final_review
```

### Complete Example: Bug Fix with TDD

```yaml
name: "Bug Fix (TDD)"
version: 1
first_task: describe_bug

tasks:
  describe_bug:
    name: "Describe Bug"
    action: prompt
    auto: false
    properties:
      prompt: |
        Describe the bug:
        - Expected behavior?
        - Actual behavior?
        - Steps to reproduce?

  investigate:
    name: "Investigate"
    action: prompt
    auto: false
    properties:
      prompt: "Bug: {{describe_bug.output}}\n\nInvestigate the root cause."

  write_test:
    name: "Write Failing Test"
    action: prompt
    auto: false
    properties:
      prompt: "Write a test that reproduces: {{investigate.output}}"

  implement_fix:
    name: "Implement Fix"
    action: prompt
    auto: false
    properties:
      prompt: "Implement a fix for the failing test."

  run_tests:
    name: "Run Tests"
    action: shell
    properties:
      command: "pytest tests/ -v"

  verify:
    name: "Verify Fix"
    action: prompt
    auto: false
    properties:
      prompt: "Tests: {{run_tests.output}}\n\nIs the bug fixed? (yes/no)"

routings:
  - from: describe_bug
    to: investigate
  - from: investigate
    to: write_test
  - from: write_test
    to: implement_fix
  - from: implement_fix
    to: run_tests
  - from: run_tests
    to: verify
  - from: verify
    to: implement_fix
    condition: route_name
    name: "no"
```

## Built-in Actions

### shell

Execute shell commands:

```yaml
tasks:
  run_tests:
    name: "Run Tests"
    action: shell
    properties:
      command: "pytest tests/"
      timeout: 300
```

### prompt

Pause for human/AI input:

```yaml
tasks:
  get_input:
    name: "Get Input"
    action: prompt
    auto: false
    properties:
      prompt: "What should we do?"
```

## Custom Actions

Create custom task actions:

```python
from zebra.tasks import TaskAction, TaskResult, ExecutionContext
from zebra.core.models import TaskInstance

class MyCustomAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        # Do something
        result = await do_work(task.properties)
        return TaskResult.ok(output=result)

# Register the action
registry.register_action("my_action", MyCustomAction)
```

## Development

```bash
# Clone and install
git clone <repo>
cd zebra-py
uv sync --extra dev

# Run tests
uv run pytest tests/ -v

# Run linter
uv run ruff check .
```

## Architecture

Zebra is a port of the Java Zebra workflow engine with modernizations:

```
┌─────────────────────────────────────┐
│         MCP Server Layer            │
│  (Claude/AI integration via tools)  │
└─────────────────────────────────────┘
                 │
┌─────────────────────────────────────┐
│       WorkflowEngine                │
│  (Process/Task lifecycle, routing)  │
└─────────────────────────────────────┘
                 │
┌─────────────────────────────────────┐
│       Pluggable Task Actions        │
│  (shell, prompt, custom actions)    │
└─────────────────────────────────────┘
                 │
┌─────────────────────────────────────┐
│       Storage Abstraction           │
│  (SQLite, In-Memory)                │
└─────────────────────────────────────┘
```

## License

Apache License 2.0

## Credits

Based on the Java Zebra workflow engine originally developed by Anite (2004) and modified by Ben Gidley (2010).
