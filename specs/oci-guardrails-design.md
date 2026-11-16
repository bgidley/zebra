# OCI billing guardrails (#279 S2)

Part of the user-instance stack in `deploy/oci/` (#279, epic #275). OpenSpec capability
`oci-billing-guardrails`.

## 1. Goal & scope

A user's Zebra must cost nothing. S1 keeps the stack itself Always Free; S2 adds guardrails in the
user's tenancy so that later drift (a console click, a paid shape in the Zebra compartment, a
PAYG upgrade) is either refused or reported:

- **Budgets** (alert only): one on the tenancy root, one on the `zebra` compartment.
- **Compartment quota** (hard stop): only the free A1 shape, the free ADB and 200 GB block storage
  in the `zebra` compartment.

Not in scope: the instance-side cost check (#284), the wizard collecting the owner email (#276),
real-tenancy verification (see §6).

## 2. Data model

No Zebra tables. Terraform resources (all in `deploy/oci/guardrails.tf`, created in the tenancy
root, `compartment_id = var.tenancy_ocid`):

| Resource | Count | Settings (locals.tf) |
|---|---|---|
| `oci_budget_budget.guardrail` | 2 (`root`, `zebra`) | `amount = 1`, `reset_period = MONTHLY`, `target_type = COMPARTMENT`, `targets = [tenancy]` / `[zebra compartment]` |
| `oci_budget_alert_rule.guardrail` | 4 per budget | ACTUAL ABSOLUTE 0.01 (any spend), ACTUAL PERCENTAGE 50, ACTUAL PERCENTAGE 100, FORECAST PERCENTAGE 100; `recipients = var.alert_email` |
| `oci_limits_quota.guardrail` | 1 (`zebra-always-free`) | statements below |

Quota statements (a later statement overrides an earlier one in the same policy):

```
zero compute-core quotas in compartment zebra
set compute-core quota standard-a1-core-count to 2 in compartment zebra
zero compute-memory quotas in compartment zebra
set compute-memory quota standard-a1-memory-count to 12 in compartment zebra
zero database quotas in compartment zebra
set database quota adb-free-count to 1 in compartment zebra
zero load-balancer quotas in compartment zebra
set block-storage quota total-storage-gb to 200 in compartment zebra
```

## 3. Interface

- Variables: `create_guardrails` (bool, default `true`), `alert_email` (string, validated; required
  when guardrails are on). Both in `schema.yaml` (group "Billing guardrails"; the email field is
  shown only when the box is ticked).
- Output `guardrails`: "Created: …" or "Skipped (create_guardrails = false): … Ask a tenancy
  administrator to re-apply …". The email itself is not echoed.
- Plan scan (`free_tier_allowlist.yaml`, `scripts/oci_plan_scan.py`): the three types are on the
  allowlist with `require` (budget amount / period / target type, the exact quota statement
  list), `one_of` (alert `type`, `threshold_type`), `nonempty` (`recipients`) and `max_count`
  rules, plus a plan-level `guardrails` section: `all_or_none` (2 budgets + 1 quota, or none) and
  `alert_rules_per_budget` (the four rules, matched as a multiset against budgets × 4).

## 4. Control flow

`create_guardrails = true` (default): preconditions check `alert_email` is set (on the budgets)
and that the parent compartment is the tenancy root (on the quota: statements name the
compartment by path, and only a root child's path is known at plan time). Then both budgets, the
eight alert rules and the quota are created alongside the stack.

`create_guardrails = false`: none are created; the stack still applies for a non-admin with
compartment-level rights (#278 option B), and the output says the guardrails were skipped.

**Tenancy-admin requirement.** Budgets and quota policies are tenancy-level objects: creating them
needs a user in the Administrators group, or a policy such as
`Allow group <g> to manage usage-budgets in tenancy` and `Allow group <g> to manage quota in tenancy`.
#278's access options must state this; a compartment-scoped grant cannot create them.

## 5. Configuration

`budget_amount` (1), `budget_alerts`, `quota_name` and `quota_statements` are locals, never
variables. The budget amount is a whole number in the tenancy's **rate-card currency** (1 GBP for a
UK tenancy, 1 USD for a US one); OCI offers no currency field.

## 6. Open questions / risks

Verified against the pinned provider schema (`oracle/oci` 7.32.0, `terraform providers schema
-json`) and the provider docs: every attribute name used on `oci_budget_budget`,
`oci_budget_alert_rule` and `oci_limits_quota`; `reset_period = MONTHLY`; alert `type`
ACTUAL / FORECAST; budget `targets` for `COMPARTMENT`. Verified against the OCI quota docs:
`set` / `zero` syntax, the "later statement supersedes" rule (with the `zero … ; set …` pattern
in Oracle's own example), family names `compute-core`, `compute-memory`, `database`,
`load-balancer`, `block-storage`, quota names `standard-a1-core-count`,
`standard-a1-memory-count`, `total-storage-gb`.

Not verifiable without a real tenancy (to be checked in the Always-Free-only test tenancy, #279
plan §2):

1. **`adb-free-count`** is listed in Oracle's ADB quota table, but its description there reads
   like a storage quota. Whether the free ADB also consumes another `database` quota (which the
   `zero` would then block) is unknown. If the free ADB is refused, add a `set` for that quota.
2. **`threshold_type` values** (`ABSOLUTE`, `PERCENTAGE`) come from the Budgets API; the provider
   docs list none. A 0.01 ABSOLUTE threshold is assumed accepted (the docs allow two decimals).
3. **Budgets and quotas on Always-Free-only accounts**: whether OCI allows them before a PAYG
   upgrade is not documented.
4. **Per-AD scope**: `standard-a1-core-count`, `standard-a1-memory-count` and `total-storage-gb`
   are availability-domain quotas, so the `set` allows 2 / 12 / 200 *per AD*. Service limits and
   S1's plan scan bound the stack itself; the quota alone would allow more in a multi-AD region.
   A `where request.ad = …` condition needs AD names at plan time; deferred.
5. **Network load balancers, NAT gateways, reserved IPs, HSM vaults** are not covered by the quota
   (family names not confirmed); S1's plan scan and the budgets cover the stack.
6. Quota policy location: created in the tenancy root (works per the docs); quotas elsewhere are
   allowed but not needed.
7. Budget alert emails go through OCI's own notifications; deliverability to the owner is not
   tested in CI.

## 7. Plan-scan and fmt follow-ups from S1

- **#298**: a boot-volume size unknown at plan time (absent from `after`, `true` in
  `after_unknown`) now fails the scan; an explicit `null` still counts OCI's 47 GB default.
- **#299**: the tree was `terraform fmt` clean in the pinned container (`fmt -check -recursive
  -diff` printed nothing). The flagged lines were correct: terraform aligns `=` only within a run
  of consecutive single-line attributes, and a blank line, comment or nested block starts a new
  run. `scripts/oci_iac_check.sh` now prints the diff and a fix hint on failure, and first
  self-tests the gate against `tests/iac/fixtures/misformatted/`.
