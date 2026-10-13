## Context

Human tasks (`auto: false`) render `task_def.properties.schema`. Only the top-level `description` and field `default`/`description` strings were template-resolved. Generated workflows therefore had no way to vary the fields themselves.

## Decisions

- **Reference, not a new property.** `schema: "{{followup_form}}"` reads naturally in YAML and reuses the template syntax workflows already use. A separate `schema_from:` key would be one more thing for the creator to learn.
- **Whole-schema reference only.** The string must be exactly one `{{...}}`. Mixing static and generated fields was considered and left out; the generating LLM can include any fixed fields itself.
- **Resolve at read time, in one helper.** The engine does not template task properties, so each consumer calls `resolve_task_schema(schema, process.properties)`. Render and submit resolve against the same properties, so they validate the same fields.
- **Fail soft.** A missing or malformed generated schema falls back to the single `response` textarea so the user is never stuck. The resolver logs a warning.
- **Safety.** Generated titles, names and descriptions go through the existing escaping in `form_tags`. Nothing new is marked safe.

## Risks

- The LLM may return a schema with a bad shape (e.g. `properties` as a list). That resolves to `None` and the fallback field is shown.
- Old workflows keep their prose questions. The creator and optimiser pick up the pattern only for new or rewritten workflows.
