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
    auto: false
    properties:
      schema:
        type: object
        title: "What feature should we implement?"
        required: [description]
        properties:
          description:
            type: string
            title: "Feature Description"
            format: multiline

  create_plan:
    name: "Create Plan"
    auto: false
    properties:
      schema:
        type: object
        title: "Create a Plan"
        description: "Requirements: {{gather_requirements.output}}"
        required: [plan]
        properties:
          plan:
            type: string
            title: "Implementation Plan"
            format: multiline

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
from zebra.core.models import TaskResult
from zebra.forms import schema_to_form, coerce_form_data, validate_form_data

async def main():
    # Initialize storage and registry
    store = SQLiteStore("workflows.db")
    await store.initialize()

    registry = ActionRegistry()
    registry.register_defaults()

    # Create engine and start workflow
    engine = WorkflowEngine(store, registry)
    definition = load_definition("my_workflow.yaml")
    process = await engine.create_process(definition)
    await engine.start_process(process.id)

    # Handle human tasks
    while True:
        pending = await engine.get_pending_tasks(process.id)
        if not pending:
            break

        task = pending[0]
        task_def = definition.tasks[task.task_definition_id]
        schema = task_def.properties.get("schema", {})
        form = schema_to_form(schema)

        # Show the form title and collect input for each field
        print(f"\n--- {form.title} ---")
        raw_data = {}
        for field in form.fields:
            label = f"{field.title} *" if field.required else field.title
            if field.enum:
                print(f"  Options: {', '.join(field.enum)}")
            raw_data[field.name] = input(f"  {label}: ")

        # Coerce and validate
        coerced = coerce_form_data(schema, raw_data)
        errors = validate_form_data(schema, coerced)
        if errors:
            for e in errors:
                print(f"  Error: {e.field} - {e.message}")
            continue  # re-prompt on error

        await engine.complete_task(task.id, TaskResult.ok(output=coerced))

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

### Human Tasks

Tasks with `auto: false` pause the workflow and wait for a person to fill in a form and submit it. The form fields are defined using standard [JSON Schema](https://json-schema.org/) in the task's `properties.schema`:

```yaml
tasks:
  describe_bug:
    name: "Describe Bug"
    auto: false
    properties:
      schema:
        type: object
        title: "Describe the Bug"
        required: [summary, severity]
        properties:
          summary:
            type: string
            title: "Summary"
            minLength: 10
            placeholder: "Brief description..."
          severity:
            type: string
            title: "Severity"
            enum: [critical, high, medium, low]
            default: medium
          details:
            type: string
            title: "Details"
            format: multiline
```

When the engine reaches this task it creates it in READY state and stops -- no action runs. An external caller (the web UI, a CLI, or an API client) picks up the task, renders a form from the schema, and submits the filled-in data back to the engine.

#### How It Works

1. Engine creates the task in READY state (no action runs).
2. Call `engine.get_pending_tasks(process_id)` to find waiting tasks.
3. Read `task_def.properties["schema"]` to get the JSON Schema.
4. Render a form (or use `schema_to_form()` from `zebra.forms` for a ready-made field list).
5. Validate and coerce the submission with `validate_form_data()` and `coerce_form_data()`.
6. Complete the task:
   ```python
   from zebra.core.models import TaskResult
   await engine.complete_task(task_id, TaskResult.ok(output=form_data))
   ```
7. The engine stores the output as `__task_output_{task_definition_id}` in process properties.
8. Downstream tasks reference it with `{{task_def_id.output}}`.

#### Supported Field Types

| Schema Type | Format / Constraint | Rendered As |
|-------------|---------------------|-------------|
| `string` | *(default)* | Text input |
| `string` | `format: multiline` | Textarea |
| `string` | `format: email` | Email input |
| `string` | `format: url` | URL input |
| `string` | `format: date` | Date picker |
| `string` | `enum: [...]` | Dropdown select |
| `boolean` | | Checkbox |
| `integer` / `number` | | Number input |
| `array` | `items.enum: [...]` | Multi-select |

Common JSON Schema constraints are supported: `required`, `minLength`, `maxLength`, `minimum`, `maximum`, `pattern`, `default`, `description`, and `placeholder` (custom extension).

#### Conditional Routing from Human Tasks

Human tasks often need to branch the workflow based on the user's answer (e.g. approve / reject). Use an `enum` field together with named routes:

```yaml
tasks:
  verify_fix:
    name: "Verify Fix"
    auto: false
    properties:
      schema:
        type: object
        title: "Verify Fix"
        required: [verified]
        properties:
          verified:
            type: string
            title: "Is the bug fixed?"
            enum: ["yes", "no"]

routings:
  - from: verify_fix
    to: complete
    condition: route_name
    name: "yes"

  - from: verify_fix
    to: implement_fix
    condition: route_name
    name: "no"
```

The web UI detects these named routes and renders separate buttons for each choice instead of a generic Submit button.

#### Form Utilities (`zebra.forms`)

The `zebra.forms` module provides helpers for working with JSON Schema forms programmatically:

```python
from zebra.forms import schema_to_form, validate_form_data, coerce_form_data

schema = task_def.properties["schema"]

# Convert schema to a list of renderable fields
form = schema_to_form(schema)
for field in form.fields:
    print(f"{field.title} ({field.widget}), required={field.required}")

# After receiving form data from the user:
raw_data = {"summary": "Login fails", "severity": "high", "details": "..."}

# Coerce HTML form strings to proper Python types
coerced = coerce_form_data(schema, raw_data)

# Validate against schema constraints
errors = validate_form_data(schema, coerced)
if errors:
    for e in errors:
        print(f"  {e.field}: {e.message}")
else:
    await engine.complete_task(task_id, TaskResult.ok(output=coerced))
```

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

Use conditions to create decision points. When a human task has an `enum` field and named routes, the user's choice determines which path the workflow takes:

```yaml
tasks:
  decision:
    name: "Make Decision"
    auto: false
    properties:
      schema:
        type: object
        title: "Review Approval"
        required: [decision]
        properties:
          decision:
            type: string
            title: "Approve this change?"
            enum: ["yes", "no"]
          comments:
            type: string
            title: "Comments"
            format: multiline

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

The `route_name` condition checks if the task result's `next_route` matches the routing's `name`. In the web UI, each named route is rendered as a separate button so the user can click "yes" or "no" directly.

### Complete Example: Feature Implementation

```yaml
name: "Feature Implementation"
version: 1
first_task: gather_requirements

tasks:
  gather_requirements:
    name: "Gather Requirements"
    auto: false
    properties:
      schema:
        type: object
        title: "Gather Requirements"
        required: [feature_description]
        properties:
          feature_description:
            type: string
            title: "Feature Description"
            description: "What feature should we implement?"
            format: multiline
            minLength: 10
          acceptance_criteria:
            type: string
            title: "Acceptance Criteria"
            format: multiline

  create_plan:
    name: "Create Plan"
    auto: false
    properties:
      schema:
        type: object
        title: "Create Implementation Plan"
        description: "Requirements: {{gather_requirements.output}}"
        required: [plan]
        properties:
          plan:
            type: string
            title: "Implementation Plan"
            format: multiline

  review_plan:
    name: "Review Plan"
    auto: false
    properties:
      schema:
        type: object
        title: "Review Plan"
        description: "Plan: {{create_plan.output}}"
        required: [decision]
        properties:
          decision:
            type: string
            title: "Approve this plan?"
            enum: ["yes", "modify"]
          feedback:
            type: string
            title: "Feedback"
            format: multiline

  implement:
    name: "Implement"
    auto: false
    properties:
      schema:
        type: object
        title: "Implement Feature"
        description: "Plan: {{create_plan.output}}"
        required: [implementation_notes]
        properties:
          implementation_notes:
            type: string
            title: "Implementation Notes"
            format: multiline

  run_tests:
    name: "Run Tests"
    action: shell
    properties:
      command: "pytest tests/"

  final_review:
    name: "Final Review"
    synchronized: true
    auto: false
    properties:
      schema:
        type: object
        title: "Final Review"
        description: "Test results: {{run_tests.output}}"
        required: [approved]
        properties:
          approved:
            type: boolean
            title: "Approve for merge?"

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
    auto: false
    properties:
      schema:
        type: object
        title: "Describe the Bug"
        required: [summary, severity]
        properties:
          summary:
            type: string
            title: "Summary"
            minLength: 10
          severity:
            type: string
            title: "Severity"
            enum: [critical, high, medium, low]
            default: medium
          expected_behavior:
            type: string
            title: "Expected Behavior"
            format: multiline
          actual_behavior:
            type: string
            title: "Actual Behavior"
            format: multiline
          steps_to_reproduce:
            type: string
            title: "Steps to Reproduce"
            format: multiline

  investigate:
    name: "Investigate"
    auto: false
    properties:
      schema:
        type: object
        title: "Investigate Root Cause"
        description: "Bug: {{describe_bug.output}}"
        required: [findings]
        properties:
          findings:
            type: string
            title: "Root Cause Analysis"
            format: multiline

  write_test:
    name: "Write Failing Test"
    auto: false
    properties:
      schema:
        type: object
        title: "Write Failing Test"
        description: "Investigation: {{investigate.output}}"
        required: [test_code]
        properties:
          test_code:
            type: string
            title: "Test Code"
            format: multiline

  implement_fix:
    name: "Implement Fix"
    auto: false
    properties:
      schema:
        type: object
        title: "Implement Fix"
        required: [fix_description]
        properties:
          fix_description:
            type: string
            title: "Fix Description"
            format: multiline

  run_tests:
    name: "Run Tests"
    action: shell
    properties:
      command: "pytest tests/ -v"

  verify:
    name: "Verify Fix"
    auto: false
    properties:
      schema:
        type: object
        title: "Verify Fix"
        description: "Test results: {{run_tests.output}}"
        required: [verified]
        properties:
          verified:
            type: string
            title: "Is the bug fixed?"
            enum: ["yes", "no"]

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

> **Note:** For human input tasks, use `auto: false` with a JSON Schema form instead of an action. See [Human Tasks](#human-tasks) above.

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
