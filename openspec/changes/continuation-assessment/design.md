## Context

The foundation commit added the `continuation_comment`, `continuation_decision` and `continuation_rationale` fields to `WorkflowRun`. `record_metrics` and `assess_and_record` copy these from process properties. A follow-up or continuation process carries `previous_run_context` (F116, extended by #134).

## Decisions

**A pass-through step, not a routing condition.** The engine's only general condition is `route_name`, and an unregistered condition defaults to *true*. A property-based condition would therefore silently send every goal down the continuation path in any registry that lacked it. Instead `assess_continuation` always follows the ethics input gate. With no `previous_run_context`, it returns `not_continuation` straight away: no LLM call and no property writes. Non-continuation goals then follow the existing `select_workflow` path unchanged.

**Placement.** The step comes after `ethics_input_gate`, so continuations still pass the ethics gate, and before selection and creation. The later `flag_concerns` and `ethics_plan_review` steps run on every route.

**Downstream compatibility.** For `same_workflow` the assessor sets `workflow_name` and a `selection` dict with the same shape as the selector's output, so later templates (`{{selection.reasoning}}`) resolve. For `new_workflow` it sets `selection` with `create_new: true` and an optional `suggested_name`, then routes to the existing `create_workflow` step. That step keeps the #122/#128 validation and truncation safeguards.

**Fallbacks.** `existing_workflow` is the safe default, because the selector can still choose anything. It is used when the provider is missing, the LLM call fails, the JSON cannot be parsed, the decision is unknown, or a `same_workflow` target is no longer in the `WorkflowLibrary` (`context.extras["__workflow_library__"]`, or `available_workflows` when there is no library). The recorded decision is the route actually taken, and the rationale notes the fallback.

**Model resolution.** Same as the ethics gate: task `provider`/`model` > process `__llm_provider_name__`/`__llm_model__` > `anthropic` with the provider's default model.

## Risks

- `same_workflow` re-runs the whole previous workflow and does not resume it. The previous run's output and the user's comment reach the child workflow through `with_previous_run`.
- #134 is changing `previous_run_context` (adding task progress). The assessor accepts `task_progress` or `tasks` lists and works without either.
