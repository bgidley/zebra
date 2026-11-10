> Branch: `f279a/oci-stack-skeleton`. Commits `Part of #279` (S1 of six slices).

## 1. Stack

- [x] 1.1 `deploy/oci/` Terraform: compartment, VCN (443 only), A1 2/12 with ephemeral IP, free ADB (mTLS + IP ACL), DEFAULT vault + SOFTWARE key + generated admin secret, `zebra-models` bucket
- [x] 1.2 Limits as locals with `precondition`s; only region, compartment, SSH key, domain, release channel as variables
- [x] 1.3 `schema.yaml` Resource Manager form; provider lock for arm64 + amd64

## 2. Guard

- [x] 2.1 `free_tier_allowlist.yaml` and `scripts/oci_plan_scan.py`
- [x] 2.2 `deploy/oci/tests/stack.tftest.hcl` with `mock_provider "oci"`
- [x] 2.3 `scripts/oci_iac_check.sh`: fmt, init, validate, test, credential-free plan, scan (pinned container)
- [x] 2.4 `tests/iac/`: clean plan passes, one bad plan per rule fails, variables and schema in step

## 3. Delivery

- [x] 3.1 Additive `iac` CI job; `tests` in pytest `testpaths`
- [x] 3.2 `specs/zebra-as-is.md` updated
