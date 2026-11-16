## Why

The Zebra OCI stack (#279) must never cost the user money. S1 keeps the stack itself inside
Always Free, but nothing stops the tenancy (or someone with console access to the Zebra
compartment) from launching a paid shape later, and nothing tells the owner if spend starts. #279's
2026-11-04 decision asks for billing guardrails created by the stack: budgets that email the owner
on any spend and a compartment quota that refuses non-free resources. This is slice S2. It also
closes two S1 follow-ups ruled on the outcome review: #298 (an unknown boot-volume size must fail
the plan scan, not count as 47 GB) and #299 (the fmt gate must show its diff and prove it fails).

## What Changes

- **Budgets**: two OCI Budgets (monthly, amount 1 in the tenancy's rate-card currency), one
  targeting the root compartment and one the `zebra` compartment, each with four alert rules:
  ACTUAL above 0.01 (absolute, i.e. any spend), ACTUAL 50 %, ACTUAL 100 %, FORECAST 100 %,
  emailing a new `alert_email` variable.
- **Compartment quota** `zebra-always-free` (in the tenancy): zero `compute-core`,
  `compute-memory`, `database` and `load-balancer` quotas in the `zebra` compartment, then set
  `standard-a1-core-count` 2, `standard-a1-memory-count` 12, `adb-free-count` 1 and
  `block-storage total-storage-gb` 200.
- **`create_guardrails`** variable (default true). Budgets and quotas live in the tenancy and need
  a tenancy administrator; a non-admin sets it false and the stack skips them, saying so in a
  `guardrails` output. With guardrails on, `alert_email` is required and the parent compartment
  must be the tenancy root (quota statements name the compartment by path), checked by
  `precondition`s.
- **Plan scan**: `oci_budget_budget`, `oci_budget_alert_rule` and `oci_limits_quota` join the
  allowlist with their own rules (exact amount, period, target type, quota statements;
  `one_of` and `nonempty` rule keys) and a plan-level `guardrails` check (all or none; exactly
  the four alert rules per budget). An unknown boot-volume size now fails the scan (#298).
- **fmt gate** (#299): `scripts/oci_iac_check.sh` prints the fmt diff and a fix hint on failure,
  and first proves the gate rejects a deliberately mis-formatted fixture.
- Design note `specs/oci-guardrails-design.md` (tenancy-admin requirement, unverifiable items).

## Capabilities

### New Capabilities
- `oci-billing-guardrails`: budgets, alert rules and the compartment quota in the OCI stack, and
  their plan-scan rules.

### Modified Capabilities
- `oci-provision-stack`: two new variables (`create_guardrails`, `alert_email`); the plan scan
  fails on an unknown boot-volume size; the fmt gate shows its diff and is self-tested.

## Impact

`deploy/oci/` (new `guardrails.tf`, variables, schema, outputs, allowlist, tests),
`scripts/oci_plan_scan.py`, `scripts/oci_iac_check.sh`, `tests/iac/`. No application code, data
model or setting changes. Nothing is applied to any tenancy; real-tenancy checks (the quota
refusing a paid shape, budgets on an Always-Free-only account) are deferred to the tenancy test
run in the #279 plan.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | The stack plans exactly the agreed guardrails | `terraform test` (mocked provider) and the CI plan: two monthly budgets of 1 (root, `zebra`), four alert rules each (ACTUAL 0.01 absolute, 50 %, 100 %; FORECAST 100 %) to `alert_email`, one quota with the exact statement list |
| O2 | The plan scan rejects any weakened or partial guardrail | `tests/iac/`: one bad plan per rule (amount, period, target type, missing/extra/changed alert rule, no recipients, changed quota statement, second quota, budgets without quota) fails; the clean plan passes |
| O3 | A non-admin can still apply, and is told guardrails were skipped | `create_guardrails = false` plans no budget or quota and the `guardrails` output says skipped and why; guardrails on without an email or under a non-root parent fail at plan with a clear message |
| O4 | S1 follow-ups closed: unknown boot size fails, fmt gate shows its diff | bad-plan test for an unknown boot-volume size (#298); `oci_iac_check.sh` self-test rejects a mis-formatted fixture and prints its diff, the tree passes (#299) |
