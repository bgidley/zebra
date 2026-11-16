## Context

S1 (`oci-provision-stack`) shipped an Always Free Resource Manager stack and a credential-free
plan scan. #279's 2026-11-04 decision adds billing guardrails created by the stack. Full design:
`specs/oci-guardrails-design.md`.

## Goals / Non-Goals

**Goals:** budgets that email the owner on any spend (actual and forecast) on the tenancy and the
Zebra compartment; a compartment quota that refuses non-free shapes and billable services; a
non-admin path that skips them and says so; plan-scan rules so they cannot be weakened quietly.
Close #298 and #299.

**Non-Goals:** the instance-side cost check (#284); collecting the email in the wizard (#276);
applying anything to a real tenancy.

## Decisions

- **Resources** `oci_budget_budget` ×2, `oci_budget_alert_rule` ×8, `oci_limits_quota` ×1, all in
  the tenancy root. Attribute names checked against the pinned provider schema (7.32.0).
- **Values are locals** (amount 1, thresholds, statements); only `create_guardrails` and
  `alert_email` are variables, neither of which can reach a paid resource.
- **Quota names the compartment by path** (`in compartment zebra`), which is only known at plan
  time when the parent is the tenancy root; a precondition enforces that when guardrails are on.
  Alternative (a parent-name lookup) would make the plan call the OCI API and break the
  credential-free CI plan.
- **Plan scan stays data-driven**: new generic rule keys `one_of` and `nonempty`; list-valued
  `require` for the statements; a plan-level `guardrails` section (all or none; alert rules
  matched as a multiset, since `budget_id` is unknown at plan time).
- **#298**: unknown (in `after_unknown`, or absent from `after`) boot size fails; explicit null
  keeps the 47 GB default.
- **#299**: tree already fmt clean; gate now prints the diff and self-tests on a fixture.

## Risks / Trade-offs

- Quota names `adb-free-count` and the per-AD scope of A1 / storage quotas are unverified in a
  real tenancy (design §6). Budgets and quotas on Always-Free-only accounts are undocumented.
- Root-parent requirement narrows where guardrails can be used; non-root users set
  `create_guardrails = false`.
