# oci-billing-guardrails Specification

## Purpose
Billing guardrails in the Zebra OCI stack (#279 S2): budgets that email the owner on any spend, a compartment quota that refuses non-free resources, a skip path for non-admins, and plan-scan rules that keep them from being weakened.

## Requirements

### Requirement: Budgets alert the owner on any spend
When `create_guardrails` is true the stack SHALL create, in the tenancy root, two monthly budgets
of amount 1 (rate-card currency) targeting the tenancy root and the `zebra` compartment, each
with exactly four alert rules: ACTUAL above 0.01 absolute, ACTUAL 50 %, ACTUAL 100 % and
FORECAST 100 %, all emailing `alert_email`.

#### Scenario: Default plan
- **WHEN** the stack is planned with guardrails on and an alert email
- **THEN** the plan has two budgets of 1 per month and eight alert rules with exactly those
  types and thresholds, all to the alert email

#### Scenario: No email
- **WHEN** guardrails are on and `alert_email` is empty
- **THEN** a precondition fails the plan saying the email is required

### Requirement: Compartment quota refuses non-free resources
When `create_guardrails` is true the stack SHALL create quota `zebra-always-free` in the tenancy
root that zeroes the `compute-core`, `compute-memory`, `database` and `load-balancer` families
in the `zebra` compartment and then sets `standard-a1-core-count` 2,
`standard-a1-memory-count` 12, `adb-free-count` 1 and `block-storage total-storage-gb` 200.

#### Scenario: Statements in the plan
- **WHEN** the stack is planned with guardrails on
- **THEN** the quota's statements are exactly that list, in that order

#### Scenario: Non-root parent
- **WHEN** guardrails are on and the parent compartment is not the tenancy root
- **THEN** a precondition fails the plan, telling the user to pick the root or turn guardrails off

### Requirement: Non-admins can skip the guardrails
`create_guardrails` (default true) SHALL let a user without tenancy-admin rights apply the stack
without budgets or quota, and the `guardrails` output SHALL say whether they were created or
skipped, and who can add them.

#### Scenario: Skipped
- **WHEN** the stack is planned with `create_guardrails = false`
- **THEN** no budget, alert rule or quota is planned and the output starts "Skipped" and names a
  tenancy administrator

### Requirement: Plan scan enforces the guardrails
The allowlist SHALL list `oci_budget_budget`, `oci_budget_alert_rule` and `oci_limits_quota` with
their own rules, and the scan SHALL fail when a budget's amount, period or target type changes,
an alert rule's type or threshold type is outside the allowed values or it has no recipients, the
quota statements differ, more than the allowed count is planned, the guardrails are partial, or
any budget lacks exactly the four alert rules. A plan with no guardrail resources SHALL pass.

#### Scenario: Weakened guardrail
- **WHEN** a plan raises a budget amount, drops or changes an alert rule, empties recipients,
  edits a quota statement, adds a second quota, or has budgets without the quota
- **THEN** the scan fails and names the resource and rule

#### Scenario: Non-admin plan
- **WHEN** the plan has none of the guardrail resources
- **THEN** the scan passes
