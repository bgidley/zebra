> Branch: `f279b/oci-guardrails`. Commits `Part of #279` (S2), `Closes #298`, `Closes #299`.

## 1. Guardrails

- [x] 1.1 `deploy/oci/guardrails.tf`: two budgets, four alert rules each, `zebra-always-free` quota; values in `locals.tf`
- [x] 1.2 `create_guardrails` and `alert_email` variables, `schema.yaml`, `guardrails` output; preconditions for email and root parent
- [x] 1.3 `terraform test` runs: defaults, non-admin skip, missing email, non-root parent, bad email

## 2. Plan scan

- [x] 2.1 Allowlist entries and `one_of` / `nonempty` / list `require` / plan-level `guardrails` rules
- [x] 2.2 Bad-plan tests per guardrail rule; clean plan regenerated; no-guardrails plan passes
- [x] 2.3 Unknown boot-volume size fails the scan (#298)

## 3. fmt gate (#299)

- [x] 3.1 Reproduce with `terraform fmt -check -recursive -diff` in the pinned container (clean)
- [x] 3.2 `oci_iac_check.sh` prints the diff and a hint on failure; self-test on a mis-formatted fixture

## 4. Delivery

- [x] 4.1 `specs/oci-guardrails-design.md`, `specs/AGENTS.md`, `specs/zebra-as-is.md`
