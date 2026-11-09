# onboarding-access Specification

## Purpose
TBD - created by archiving change onboarding-access-threat-model. Update Purpose after archive.

## Requirements

### Requirement: Access design documented
The onboarding design SHALL specify the anonymous session model, the access options, the callback
protocol and a threat model covering assets, attackers and mitigations before build slices start.

#### Scenario: Threat model present
- **WHEN** a reviewer opens `specs/onboarding-design.md`
- **THEN** it lists assets, attackers T1-T6 and a mitigation for each

### Requirement: Policy scoped to one compartment
The documented access policy SHALL grant only within one compartment, and SHALL show tenancy-level
grants (budgets, quotas, dynamic group) separately.

#### Scenario: Tenancy-level grants separate
- **WHEN** the policy text is read
- **THEN** the compartment-scoped block contains no `in tenancy` statement and the two tenancy
  statements appear in their own block
