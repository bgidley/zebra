# ethics-outcome-recording Specification

## Purpose
Make every ethics outcome in the goal loop durable and visible: the post-execution review is audited, and rejections record which gate rejected the goal and why (GitLab #143).

## Requirements

### Requirement: Post-execution ethics review is recorded to the audit log

After the `ethics_post_review` LLM step, the Agent Main Loop SHALL run `record_ethics_review`, which normalises `ethics_post_assessment` into `{ethical, overall_reasoning, concerns, recommendations}`, stores it back on the process, and appends an `EthicsAuditEntry` with `check_type="post_review"` and `approved` equal to `ethical`.

#### Scenario: Ethical review is audited

- **WHEN** `ethics_post_assessment` is `{"ethical": true, "overall_reasoning": "fine"}`
- **THEN** an audit entry is appended with `check_type="post_review"`, `approved=True`, `overall_reasoning="fine"`

#### Scenario: Unparseable review fails closed

- **WHEN** `ethics_post_assessment` is a non-JSON string
- **THEN** the normalised assessment has `ethical=False` and the audit entry has `approved=False` with reasoning noting the review could not be parsed

#### Scenario: Missing audit store is tolerated

- **WHEN** `__ethics_audit_store__` is absent from `context.extras`
- **THEN** the action logs a warning and returns success with the normalised assessment

### Requirement: Conceptual memory update does not depend on the post-execution review

The Agent Main Loop SHALL run `update_conceptual_memory` before `ethics_post_review`, so a failing review cannot prevent the memory update.

#### Scenario: Review failure after memory update

- **WHEN** `ethics_post_review` fails
- **THEN** `update_conceptual_memory` has already completed for that run

### Requirement: Ethics rejections record the rejecting gate and reason

The `ethics_rejection` task SHALL run `record_ethics_rejection`, which sets process property `ethics_rejection = {gate, reasoning, concerns}` where `gate` is `dilemma_resolution` if the human declined an escalated dilemma, `plan_review` if the plan assessment was not approved, otherwise `input_gate`.

#### Scenario: Input gate rejection

- **WHEN** the input gate rejects with reasoning "Rejected on ethical grounds"
- **THEN** `ethics_rejection.gate == "input_gate"` and `ethics_rejection.reasoning == "Rejected on ethical grounds"`

#### Scenario: Plan review rejection

- **WHEN** the input gate approves and the plan review rejects
- **THEN** `ethics_rejection.gate == "plan_review"` with the plan assessment's reasoning and concerns

#### Scenario: Declined dilemma

- **WHEN** the human resolves an escalated dilemma with `decline` and note "not worth it"
- **THEN** `ethics_rejection.gate == "dilemma_resolution"` and the reasoning includes the note

### Requirement: Rejection reason is surfaced to callers and the UI

`AgentLoop.process_goal()` SHALL return `AgentResult.ethics_rejection` set from the process property and `error` of the form `Rejected by ethics <gate>: <reasoning>`. The run detail and run pending pages SHALL display the rejection reason, or the post-review verdict with its concerns and recommendations.

#### Scenario: Rejected goal result

- **WHEN** a goal is rejected by the input gate
- **THEN** `AgentResult.success` is False, `AgentResult.ethics_rejection["gate"] == "input_gate"`, and `AgentResult.error` starts with "Rejected by ethics input_gate"

#### Scenario: Run page shows rejection

- **WHEN** a user opens the run page for a rejected goal
- **THEN** an Ethics panel shows the rejecting gate and its reasoning
