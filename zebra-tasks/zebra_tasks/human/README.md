# Human Interaction Task Actions

This module provides task actions for human-in-the-loop workflows in Zebra.

## Overview

Human interaction actions enable workflows to pause and wait for human input or acknowledgment. These are essential for workflows that require:

- User input collection
- Confirmation dialogs
- Progress reporting
- Interactive decision-making

## Available Actions

### DataEntryAction

Request structured data input from a human user.

**Action name:** `data_entry`

**How it works:**
1. Task starts and enters RUNNING state
2. Field schema is stored in process properties for external systems to read
3. Task waits until `engine.complete_task(task_id, result)` is called
4. Collected data is validated and stored in process properties

**Properties:**

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `title` | string | No | Title for the data entry form (default: "Data Entry") |
| `fields` | list | Yes | List of field definitions (see below) |
| `output_key` | string | No | Where to store collected data (default: "user_input") |
| `timeout` | number | No | Optional timeout in seconds (not enforced by action) |

**Field Definition:**

Each field in the `fields` list should have:

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `name` | string | Yes | Field identifier (used as key in result) |
| `label` | string | Yes | Human-readable label |
| `type` | string | No | Field type: "text", "number", "boolean", "date", "select" (default: "text") |
| `required` | boolean | No | Whether field is required (default: false) |
| `default` | any | No | Default value |
| `description` | string | No | Help text |
| `options` | list | No* | List of options (*required for "select" type) |

**Example Workflow:**

```yaml
tasks:
  get_user_info:
    name: "Collect User Information"
    action: data_entry
    auto: true
    properties:
      title: "User Registration"
      fields:
        - name: username
          label: "Username"
          type: text
          required: true
        - name: age
          label: "Age"
          type: number
          required: true
        - name: email
          label: "Email Address"
          type: text
          required: false
        - name: plan
          label: "Select Plan"
          type: select
          options: ["Free", "Pro", "Enterprise"]
          required: true
      output_key: user_data
```

**External Completion Example:**

```python
from zebra.core.models import TaskResult

# When user submits the form:
result = TaskResult.ok(output={
    "username": "john_doe",
    "age": 30,
    "email": "john@example.com",
    "plan": "Pro"
})

# Complete the task
await engine.complete_task(task_id, result)
```

**Retrieving Pending Data Entry:**

External systems can query pending data entry requests:

```python
# Get the data entry schema
process = await engine.store.get_process(process_id)
entry_info = process.properties.get(f"__data_entry_{task_id}__")

if entry_info:
    print(f"Title: {entry_info['title']}")
    print(f"Fields: {entry_info['fields']}")
    print(f"Status: {entry_info['status']}")  # "waiting"
```

---

### DataDisplayAction

Display structured data to a human and wait for acknowledgment.

**Action name:** `data_display`

**How it works:**
1. Task starts and enters RUNNING state
2. Template variables in data are resolved
3. Display content is stored in process properties for external systems
4. Task waits until `engine.complete_task(task_id, result)` is called
5. Acknowledgment (with optional feedback) is stored in process properties

**Properties:**

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `title` | string | Yes | Title for the display |
| `message` | string | No | Main message or description text (supports {{var}} templates) |
| `fields` | list | No* | List of field data to display (*required if no `data`) |
| `data` | dict | No* | Raw dict of data to display (*required if no `fields`) |
| `output_key` | string | No | Where to store acknowledgment (default: "display_acknowledged") |
| `require_confirmation` | boolean | No | If true, expect explicit confirmation (default: false) |
| `timeout` | number | No | Optional timeout in seconds (not enforced by action) |

**Field Definition:**

Each field in the `fields` list should have:

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `label` | string | Yes | Field label |
| `value` | any | Yes | Field value (supports {{var}} templates) |
| `format` | string | No | Display format hint: "text", "number", "currency", "date", "code" (default: "text") |

**Example Workflow:**

```yaml
tasks:
  analyze_data:
    name: "Analyze Data"
    action: llm_call
    properties:
      prompt: "Analyze: {{input_data}}"
      output_key: analysis

  show_results:
    name: "Display Analysis Results"
    action: data_display
    auto: true
    properties:
      title: "Analysis Complete"
      message: "Here are the results of the data analysis for {{user_name}}."
      fields:
        - label: "Analysis Type"
          value: "{{analysis.type}}"
        - label: "Confidence Score"
          value: "{{analysis.confidence}}"
          format: "number"
        - label: "Recommendation"
          value: "{{analysis.recommendation}}"
      require_confirmation: true
      output_key: user_acknowledged
```

**External Acknowledgment Example:**

```python
from zebra.core.models import TaskResult

# Simple acknowledgment:
result = TaskResult.ok(output={"acknowledged": True})
await engine.complete_task(task_id, result)

# With feedback:
result = TaskResult.ok(output={
    "acknowledged": True,
    "feedback": "Looks good, proceed",
    "rating": 5
})
await engine.complete_task(task_id, result)
```

**Retrieving Pending Display:**

External systems can query pending displays:

```python
# Get the display content
process = await engine.store.get_process(process_id)
display_info = process.properties.get(f"__data_display_{task_id}__")

if display_info:
    print(f"Title: {display_info['title']}")
    print(f"Message: {display_info['message']}")
    print(f"Fields: {display_info['fields']}")
    print(f"Requires confirmation: {display_info['require_confirmation']}")
```

---

## Integration Patterns

### Finding Tasks Waiting for Human Input

```python
# Get all tasks in a process
tasks = await engine.store.load_tasks_for_process(process_id)

# Filter for tasks waiting for human input
waiting_tasks = [
    task for task in tasks
    if task.state == TaskState.RUNNING and
       f"__waiting_for_human_{task.id}__" in process.properties
]
```

### Building a UI Integration

```python
from zebra.core.models import TaskState, TaskResult

async def get_pending_interactions(engine, process_id):
    """Get all pending human interactions for a process."""
    process = await engine.store.get_process(process_id)
    tasks = await engine.store.load_tasks_for_process(process_id)

    interactions = []
    for task in tasks:
        if task.state != TaskState.RUNNING:
            continue

        # Check for data entry
        entry_key = f"__data_entry_{task.id}__"
        if entry_key in process.properties:
            interactions.append({
                "type": "data_entry",
                "task_id": task.id,
                "data": process.properties[entry_key]
            })

        # Check for data display
        display_key = f"__data_display_{task.id}__"
        if display_key in process.properties:
            interactions.append({
                "type": "data_display",
                "task_id": task.id,
                "data": process.properties[display_key]
            })

    return interactions

async def handle_user_input(engine, task_id, user_data):
    """Handle user input for a data entry task."""
    result = TaskResult.ok(output=user_data)
    await engine.complete_task(task_id, result)

async def handle_user_acknowledgment(engine, task_id, feedback=None):
    """Handle user acknowledgment for a display task."""
    result = TaskResult.ok(output={
        "acknowledged": True,
        "feedback": feedback
    })
    await engine.complete_task(task_id, result)
```

### Web API Example

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

class DataEntrySubmission(BaseModel):
    task_id: str
    data: dict

class DisplayAcknowledgment(BaseModel):
    task_id: str
    feedback: str | None = None

@app.get("/process/{process_id}/pending")
async def get_pending(process_id: str):
    """Get all pending human interactions."""
    return await get_pending_interactions(engine, process_id)

@app.post("/task/submit")
async def submit_data_entry(submission: DataEntrySubmission):
    """Submit data entry."""
    await handle_user_input(engine, submission.task_id, submission.data)
    return {"status": "submitted"}

@app.post("/task/acknowledge")
async def acknowledge_display(ack: DisplayAcknowledgment):
    """Acknowledge a display."""
    await handle_user_acknowledgment(engine, ack.task_id, ack.feedback)
    return {"status": "acknowledged"}
```

## Best Practices

1. **Validation**: The actions validate field schemas, but you should also validate user input in your external system before calling `complete_task()`.

2. **Error Handling**: If user input is invalid, complete the task with `TaskResult.fail(error_message)` to allow the workflow to handle the error.

3. **Timeouts**: The `timeout` property is informational only. Implement timeout logic in your external system if needed.

4. **User Experience**: Use descriptive titles, labels, and help text to guide users through data entry.

5. **Progressive Disclosure**: Break complex forms into multiple smaller data entry tasks rather than one large form.

6. **Confirmation**: Use `require_confirmation: true` for important displays (errors, warnings, irreversible actions).

## Example: Complete Human-in-Loop Workflow

See [examples/human_interaction_example.yaml](../../examples/human_interaction_example.yaml) for a complete workflow demonstrating both data entry and data display actions.

## Testing

```bash
# Run human interaction tests
uv run pytest tests/test_human_actions.py -v
```
