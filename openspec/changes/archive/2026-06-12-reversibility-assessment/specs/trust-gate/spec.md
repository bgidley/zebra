## MODIFIED Requirements

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
