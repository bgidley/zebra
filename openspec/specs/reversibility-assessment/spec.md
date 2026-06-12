### Requirement: Task actions declare a reversibility hint
The `TaskAction` base class SHALL include a `reversibility_hint` class attribute with
value `always_reversible`, `always_irreversible`, or `context_dependent` (default
`context_dependent`), surfaced through `ActionMetadata`. The action registry SHALL expose
a query returning every registered action's hint.

#### Scenario: Default hint is context_dependent
- **WHEN** a `TaskAction` subclass does not set `reversibility_hint`
- **THEN** its metadata reports `reversibility_hint == "context_dependent"`

#### Scenario: Registry lists hints for all actions
- **WHEN** `ActionRegistry.list_reversibility_hints()` is called on a registry with
  registered actions
- **THEN** it returns a mapping of every registered action name to its hint value

#### Scenario: Read-only actions are always reversible
- **WHEN** the metadata of `file_read`, `file_info`, `file_search`, or `llm_call` is
  inspected
- **THEN** `reversibility_hint == "always_reversible"`

### Requirement: Contextual reversibility assessment
The system SHALL provide `assess_reversibility(...)` returning a
`ReversibilityAssessment` (reversible, reasoning, confidence, chain_notes, source). Hints
`always_reversible` / `always_irreversible` SHALL short-circuit without an LLM call
(`source="hint"`, confidence 1.0). For `context_dependent` actions the assessment SHALL
be an LLM judgment (default model haiku) over the action's concrete parameters that
evaluates the complete chain of consequences — an action that creates conditions for
later irreversible harm, or whose safety depends on a subsequent corrective step (the
"dropped weight" test), SHALL be classified irreversible — and SHALL judge intent and
cumulative effect rather than the step in isolation.

#### Scenario: always_reversible hint short-circuits
- **WHEN** the gated action's class declares `reversibility_hint = "always_reversible"`
- **THEN** the assessment is reversible with `source="hint"` and no LLM provider is called

#### Scenario: Context-dependent action judged from concrete parameters
- **WHEN** a `context_dependent` action is assessed and the LLM returns
  `{"reversible": false, ...}` for its parameters
- **THEN** the assessment is irreversible with `source="llm"` and carries the model's
  reasoning, confidence, and chain notes

### Requirement: Assessment failures are irreversible
When the LLM provider errors, returns unparseable JSON, or omits the verdict, the
assessment SHALL be `reversible=False` with `source="fail_closed"`. Assessment failure
SHALL never classify an action as reversible.

#### Scenario: Provider error fails closed
- **WHEN** the LLM provider raises during a context-dependent assessment
- **THEN** the returned assessment is irreversible with `source="fail_closed"`

#### Scenario: Unparseable response fails closed
- **WHEN** the LLM returns non-JSON content
- **THEN** the returned assessment is irreversible with `source="fail_closed"`

### Requirement: Assessments are audited in process properties
Every assessment performed for a trust gate SHALL be appended as a JSON-serialisable dict
to `process.properties["__trust_assessments__"]` and embedded in the corresponding
`__trust_gate_decisions__` record under `assessment`.

#### Scenario: Assessment recorded
- **WHEN** a SEMI_AUTONOMOUS trust gate triggers an assessment
- **THEN** `__trust_assessments__` gains one entry and the gate's decision record contains
  the same assessment dict
