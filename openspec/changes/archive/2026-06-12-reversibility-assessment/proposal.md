## Why

At SEMI_AUTONOMOUS, F13's `trust_gate` decides reversibility from a static, self-declared
`reversibility` property — exactly the self-classification REQ-TRUST-002's anti-gaming
clause forbids. Reversibility must be assessed contextually at execution time from the
action's concrete parameters and chain of consequences. Closes #14 (F14, REQ-TRUST-002).

## What Changes

- `TaskAction` (zebra-py) gains `reversibility_hint: ClassVar[str]` —
  `always_reversible` / `always_irreversible` / `context_dependent` (default) — surfaced
  in `ActionMetadata`; `ActionRegistry` gains `list_reversibility_hints()` and
  `get_action_class()`.
- New assessor `zebra_tasks/agent/reversibility.py`: `ReversibilityAssessment`
  (reversible, reasoning, confidence, chain_notes, source) and
  `assess_reversibility(...)` — hints short-circuit; `context_dependent` actions get an
  LLM judgment (default haiku) framed on concrete parameters, the complete chain of
  consequences, the Asimov "dropped weight" test, and anti-gaming (intent and cumulative
  effect, not steps in isolation). Assessor fails closed to irreversible.
- **BREAKING** (behaviour, trust-gate spec MODIFIED): at SEMI_AUTONOMOUS the gate now
  always assesses — the static `reversibility: reversible` declaration no longer grants
  `proceed`; it becomes prompt context only. New optional gate input `target_task_id`
  points at the gated task so the assessor sees its action class and resolved parameters.
- Assessments audited to `process.properties["__trust_assessments__"]` and embedded in
  the existing `__trust_gate_decisions__` records.
- Explicit `always_reversible` hints on read-only actions (`file_read`, `file_info`,
  `file_search`, `llm_call`).
- E2E (issue #14 criterion): file delete under a protected path prefix classified
  irreversible → gate forces approval; same delete under /tmp → proceeds.

## Capabilities

### New Capabilities
- `reversibility-assessment`: per-action reversibility hints, registry query, and the
  contextual runtime assessor feeding trust-gate decisions.

### Modified Capabilities
- `trust-gate`: SEMI_AUTONOMOUS routing is now assessment-driven; the static declaration
  no longer bypasses assessment.

## Impact

- `zebra-py/zebra/tasks/base.py`, `zebra-py/zebra/tasks/registry.py` (additive).
- `zebra-tasks/zebra_tasks/agent/reversibility.py` (new),
  `zebra_tasks/agent/trust_gate.py` (assessment integration), four hint annotations.
- Tests across zebra-py and zebra-tasks; `specs/zebra-as-is.md`, `zebra-tasks/AGENTS.md`,
  root `AGENTS.md` checklist.
- No Django/web changes, no migrations, no new dependency edges (gate reaches the
  registry via `context.engine.actions`).

## Non-goals

- No `block` route, no workflow-level cumulative-effect analysis beyond what the prompt
  frames (full anti-gaming across agent-authored workflows is later phase work).
- No promotion UI (F15), pause-all (F16), freeing (F17); agent main loop unchanged.
