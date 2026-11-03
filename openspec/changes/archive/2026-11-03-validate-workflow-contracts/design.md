## Context

`validate_definition` (loader.py) checks graph shape only. Templates are resolved lazily by
`ExecutionContext.resolve_template`, which returns `""` for anything missing. Task outputs land in
`__task_output_<id>`; actions already declare `outputs` as `ParameterDef`.

## Decisions

- **One module, `zebra/definitions/contracts.py`**, holding `validate_contracts`; the loader's
  `validate_definition` stays untouched so existing callers keep their behaviour.
- **Reference extraction**: regex `{{\s*([\w.]+)\s*}}` over all string values in task `properties`
  (recursive). Root is classified as a task id (output), a process property declared in the
  definition's `properties`, a runtime key (`__`-prefixed or a known set such as `goal`), else
  unknown. Unknown roots are `warning`s unless they look like a task id typo (edit distance) - keeps
  false positives low because processes get properties from callers.
- **Path availability**: a forward dataflow over routings: `available(task)` = intersection of
  `available(pred)` ∪ {pred} over incoming routings (union for non-synchronized tasks reached by
  any single path is the *possible* set). Referenced task in *must* set = ok; only in *may* set =
  warning; in neither = error. Cycles are handled by iterating to a fixpoint.
- **Run time**: `resolve_template` gains an optional collector; misses append to
  `process.properties["__contract_violations__"]` (JSON-serializable list of `{task, ref}`).
  `strict_templates` is read from the process properties, else the definition's `properties` (create_process does not copy definition properties onto the process). Under strict mode `resolve_template` raises `TemplateResolutionError`, which the engine turns into a failed task.
- **Task-output roots**: a `{{x.output}}` whose root is a process property written by a task `*_key` property (e.g. `output_key: execution_result`) is a property reference, not a task reference.
- **Deferred**: checking `{{task.output.key}}` against an action's declared `outputs` (the runtime does not resolve that form, and `ParameterDef` outputs describe the action result, not its keys).
- **Schema validation**: `jsonschema` is *not* a dependency (`zebra.forms` hand-rolls its checks), so `validate_output_schema` in `contracts.py` implements the small subset needed (type, enum, required, properties, items) rather than adding one.
- **Library gate**: `WorkflowLibrary.save()` already owns writes; it calls `validate_contracts` and
  raises on `error` findings only.

## Risks

- False positives on dynamic properties break optimizer saves: mitigated by only erroring on task
  references, never on bare property names.
- Built-in workflows may need small fixes; tracked in tasks.
