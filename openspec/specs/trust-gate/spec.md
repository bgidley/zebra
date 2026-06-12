### Requirement: trust_gate routes by trust level
The system SHALL provide a `trust_gate` task action (entry point `zebra.tasks`) that
reads the trust level for the resolved (user, domain) pair from
`context.extras["__trust_store__"]` and sets `next_route` as follows: `SUPERVISED` →
`approve`; `SEMI_AUTONOMOUS` → `proceed` when a contextual reversibility assessment
(REQ-TRUST-002) classifies the gated action as reversible, otherwise `approve`;
`AUTONOMOUS` → `proceed`. The gate MAY identify the gated action via a `target_task_id`
property naming a task definition in the same workflow; its action class hint and
template-resolved parameters feed the assessment. A static `reversibility` task property
SHALL be passed to the assessment as declared context only and SHALL NOT by itself cause
`proceed`. The gate SHALL NOT perform assessments at SUPERVISED or AUTONOMOUS.

#### Scenario: SUPERVISED routes to approval
- **WHEN** a `trust_gate` task with `domain: code` runs for a user whose `code` domain is
  SUPERVISED
- **THEN** the task succeeds with `next_route="approve"` and no assessment is performed

#### Scenario: AUTONOMOUS proceeds
- **WHEN** the user's `code` domain is AUTONOMOUS
- **THEN** the gate succeeds with `next_route="proceed"` and no assessment is performed

#### Scenario: SEMI_AUTONOMOUS with reversible assessment proceeds
- **WHEN** the user's `code` domain is SEMI_AUTONOMOUS and the assessment of the gated
  action returns reversible
- **THEN** the gate succeeds with `next_route="proceed"`

#### Scenario: SEMI_AUTONOMOUS with irreversible assessment requires approval
- **WHEN** the user's `code` domain is SEMI_AUTONOMOUS and the assessment returns
  irreversible (including fail-closed assessments)
- **THEN** the gate succeeds with `next_route="approve"`

#### Scenario: Static declaration alone does not grant proceed
- **WHEN** the user's domain is SEMI_AUTONOMOUS, the gate task declares `reversibility:
  reversible`, and the contextual assessment classifies the action as irreversible
- **THEN** the gate routes to `approve`

#### Scenario: Protected-path file delete forces the gate
- **WHEN** a SEMI_AUTONOMOUS workflow's gate targets a `file_delete` task whose path is
  under a protected prefix and the assessment classifies it irreversible
- **THEN** the workflow pauses at the human approval task; the same workflow deleting a
  temp path assessed reversible proceeds without approval

### Requirement: trust_gate fails closed
When the trust level cannot be determined — `__trust_store__` missing from extras, no
resolvable user id (task property `user_id` then process property `__user_id__`), a store
error, or an unrecognised level value — the gate SHALL behave as SUPERVISED and route to
`approve`, logging a warning. Inability to verify trust SHALL never grant autonomy.

#### Scenario: Missing trust store routes to approval
- **WHEN** a `trust_gate` task runs in an engine without `__trust_store__` in extras
- **THEN** the gate succeeds with `next_route="approve"` and logs a warning

#### Scenario: Missing user id routes to approval
- **WHEN** neither the `user_id` task property nor `__user_id__` process property
  resolves to an integer
- **THEN** the gate succeeds with `next_route="approve"`

#### Scenario: Missing domain fails the task
- **WHEN** a `trust_gate` task has no `domain` property
- **THEN** the task fails with an error naming the missing property

### Requirement: Gate decisions are recorded for audit
Every `trust_gate` execution SHALL append a JSON-serialisable decision record — task id,
domain, user id, trust level, reversibility declaration, chosen route, reason, and ISO
timestamp — to `process.properties["__trust_gate_decisions__"]`, and SHALL return the
same record as the task output.

#### Scenario: Decision appended to process properties
- **WHEN** two `trust_gate` tasks execute in one process
- **THEN** `__trust_gate_decisions__` holds two records in execution order, each with
  domain, level, route, reason, and timestamp

### Requirement: Approval pause and resume via human task
A workflow SHALL be able to pause on a failed trust check by routing the gate's `approve`
route to an `auto: false` human task; completing that task via
`engine.complete_task(...)` SHALL resume the workflow on the chosen route.

#### Scenario: Workflow pauses then resumes after approval
- **WHEN** a workflow's `trust_gate` routes to `approve` and the engine processes the
  workflow
- **THEN** the human approval task is in READY state and the process remains RUNNING
  (paused), and after `complete_task` is called with the approval route the downstream
  task executes and the process reaches COMPLETE
