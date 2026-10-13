## Why

Workflows that ask follow-up questions built from earlier answers (e.g. *Gear Requirements Gathering* → *Follow-up Questions*) can only put the questions in the form description as prose, with a single "answer by number" textarea. A human task's schema is fixed when the workflow is written, so the questions can't become form fields. Issue #179.

## What Changes

- A human task's `properties.schema` may be a single `{{reference}}` (`{{key}}`, `{{key.field}}` or `{{task_id.output}}`). It is resolved against process properties when the form is rendered or submitted, so an earlier `llm_call` with `response_format: json` can write the form: one field per question.
- `zebra.forms.resolve_task_schema()` does the resolution. It accepts a dict, a JSON string (optionally in a code fence) or a task output wrapping either under `response`. Anything without a non-empty `properties` object resolves to `None`.
- Every schema consumer uses it: the web form and submit, the pending-task lists, `POST /api/tasks/<id>/complete/` validation, `GET /api/processes/<id>/pending-tasks/` (new resolved `schema` key) and `execute_goal_workflow`'s `user_inputs`.
- An unresolvable reference falls back to the single `response` field, as for tasks with no schema.
- The form page no longer shows a generated schema as a raw "prior output".
- The workflow creator prompt teaches the pattern. `check_generated_workflow` rejects a string `schema` that is not a single reference.

## Capabilities

### New Capabilities
- `dynamic-human-forms`: human-task form schemas generated at runtime.

### Modified Capabilities
<!-- none -->

## Impact

- `zebra-py/zebra/forms.py`, `zebra-agent-web/zebra_agent_web/api/web_views.py`, `api/views.py`, `zebra-tasks/zebra_tasks/agent/creator.py`, `agent/execute_workflow.py`.
- Backward compatible: static dict schemas behave as before. No migrations.
- Existing library workflows (e.g. *Gear Requirements Gathering*) keep their prose questions until they are recreated or optimised.
