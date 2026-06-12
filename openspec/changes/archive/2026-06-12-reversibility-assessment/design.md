## Context

REQ-TRUST-002 requires runtime, contextual reversibility classification feeding the trust
gate. F13 shipped the gate with a static `reversibility` property as a placeholder. The
codebase already has: class-level action metadata (`description`/`inputs`/`outputs` +
`get_metadata()` in `zebra-py/zebra/tasks/base.py`), an LLM-gate pattern with JSON
responses and provider resolution (`zebra_tasks/agent/ethics_gate.py`), and
`ExecutionContext.engine` giving gate code access to the action registry.

## Goals / Non-Goals

**Goals:** action-level hints + registry query; LLM contextual assessor (haiku default,
fail-closed); gate integration where the assessment is authoritative at SEMI_AUTONOMOUS;
audited assessments; issue #14 e2e.

**Non-Goals:** cross-workflow cumulative analysis, `block` route, any UI.

## Decisions

1. **Hint is a plain `ClassVar[str]`, not an enum** — matches the existing metadata style
   (`description` is a bare str); values documented and surfaced via `ActionMetadata`.
   Validation happens where it matters (assessor treats anything unrecognised as
   `context_dependent`).
2. **Assessor lives in zebra-tasks, hint in zebra-py.** The hint is engine-level metadata
   (REQ says "TaskAction base class includes..."); the assessor needs LLM providers,
   which only zebra-tasks has. `ReversibilityAssessment` is a dataclass in the assessor
   module with `to_dict()` for process-property storage.
3. **Gate reaches the registry via `context.engine.actions`** (new
   `get_action_class()`), not a new extras key — the engine is already in
   `ExecutionContext`; no wiring changes in zebra-agent-web.
4. **Assessment is authoritative at SEMI_AUTONOMOUS** (user decision): the static
   `reversibility` property becomes prompt context ("workflow-declared reversibility")
   and never short-circuits. Only action-class hints short-circuit — they are authored in
   trusted code, not by the agent. This MODIFIES the F13 trust-gate requirement.
5. **`target_task_id` identifies the gated action.** The gate resolves the sibling task
   definition from `context.process_definition.tasks`, template-resolves its properties
   (string values only, via `context.resolve_template`), and passes action name, hint,
   and parameters to the assessor. Without `target_task_id` the LLM judges from
   `action_description` alone; with neither, fail closed (approve) as today.
6. **Fail closed, opposite of ethics_gate.** Provider errors and unparseable JSON yield
   `reversible=False, source="fail_closed"`. The ethics gate's fail-open default is a
   deliberate contrast documented there; a trust assessor that fails open would let an
   outage grant autonomy.
7. **Haiku by default** (user decision): classification is a short structured judgment;
   override via the gate task's `model` property, then `__llm_model__`, as elsewhere.

## Data Model Changes

None persistent. New appended process property `__trust_assessments__`; existing
`__trust_gate_decisions__` records gain an `assessment` field. `ActionMetadata` gains
`reversibility_hint`.

## API / Interface Changes

- `TaskAction.reversibility_hint` ClassVar; `ActionMetadata.reversibility_hint` field.
- `ActionRegistry.list_reversibility_hints() -> dict[str, str]`,
  `ActionRegistry.get_action_class(name) -> type[TaskAction]`.
- `trust_gate` new optional inputs: `target_task_id`, `model`. Behaviour change at
  SEMI_AUTONOMOUS (see Decision 4). Routes unchanged (`proceed`/`approve`).
- `assess_reversibility()` public helper for F15+ callers.

## Risks / Trade-offs

- [LLM cost on every undetermined SEMI_AUTONOMOUS gate] → hints short-circuit the common
  read-only cases; haiku keeps the rest cheap; SUPERVISED/AUTONOMOUS never assess.
- [LLM misclassification] → fail-closed default plus confidence recorded for audit;
  threshold-based policies can come later.
- [Existing workflows relying on `reversibility: reversible`] → behaviour change is
  spec-MODIFIED and called out in the commit; only test workflows use it today.

## Spec Updates

- New `openspec/specs/reversibility-assessment/spec.md` (on archive).
- MODIFIED requirement in `openspec/specs/trust-gate/spec.md`.
- `specs/zebra-as-is.md` trust-model paragraph + F12–F17 table.

## Open Questions

- None blocking. F15 may reuse `assess_reversibility` evidence in promotion requests.
