## Why

Onboarding (#275) gives each user their own Zebra in their own OCI tenancy, and the epic's hard
rule is that it stays inside Oracle's Always Free tier. #279 builds that as a Resource Manager
stack; this is slice S1: the Terraform skeleton plus a CI guard that proves, on every pipeline
and without any OCI credentials, that the stack plans only Always Free resources. Later slices
add billing guardrails (S2), first boot (S3), setup token and TLS (S4), first run (S5) and destroy
checks (S6).

## What Changes

- **`deploy/oci/`** Terraform stack: a `zebra` compartment; a VCN with one public subnet,
  internet gateway and a security list open on TCP 443 only; one Arm A1 instance
  (`VM.Standard.A1.Flex`, 2 OCPU / 12 GB, 100 GB boot, Oracle Linux 9) with an **ephemeral**
  public IP; the Always Free Autonomous Database (`is_free_tier`, 26ai, public endpoint with mTLS
  required and an access list of the instance IP only, outside the VCN); a DEFAULT vault with a
  SOFTWARE key and a Vault-generated ADB admin password (`secret_id`, never in config or
  outputs); a private `zebra-models` bucket. Default region `uk-london-1`.
- Shape, size, DB tier, vault and key type are **locals**, never variables; `precondition`
  blocks re-assert the free limits. Variables: region, parent compartment, optional SSH key
  (port 22 stays closed), optional domain, release channel.
- **`schema.yaml`** Resource Manager form; `free_tier_allowlist.yaml` of allowed resource types
  and per-type rules; provider lock for arm64 and amd64.
- **`scripts/oci_plan_scan.py`** scans `terraform show -json` output against the allowlist.
- **`scripts/oci_iac_check.sh`** runs fmt, init, validate, `terraform test` (mocked `oci`
  provider) and a plan with throwaway credentials (no API calls: lookups are keyed on the new
  compartment, so they defer to apply), then the scan, all in a pinned
  `hashicorp/terraform:1.12.2` container.
- **CI**: new additive `iac` job (stage `test`); `tests/` added to pytest `testpaths` so the
  scanner's cases run in `unit`.

## Capabilities

### New Capabilities
- `oci-provision-stack`: the Always Free Resource Manager stack and its plan-scan guard.

### Modified Capabilities
None.

## Impact

New `deploy/oci/`, `scripts/oci_plan_scan.py`, `scripts/oci_iac_check.sh`, `tests/iac/`,
`.gitlab-ci.yml` (`iac` job), `pyproject.toml` (`testpaths`). No application code, data model or
setting changes. Nothing is applied to any tenancy.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | The plan scanner rejects every Always Free rule breach | `tests/iac/`: one known-bad plan per rule (unlisted type, paid shape, OCPU/memory over 2/12, second instance, storage over 200 GB, `is_free_tier` false or unknown, second ADB, non-DEFAULT vault, HSM key, reserved IP, LB/NLB/NAT/DRG, archive bucket); each fails, the clean plan passes |
| O2 | The real stack plan passes the scanner with no OCI credentials | CI `iac` job: `terraform plan` + `show -json` of `deploy/oci/` with throwaway credentials and no API calls; `scripts/oci_plan_scan.py` exits 0 |
| O3 | No stack variable can reach a paid resource | Variables are only region, compartment, SSH key, domain, release channel (pytest); shape, size, DB tier, vault and key type are locals guarded by `precondition`s; `terraform test` (mocked `oci` provider) asserts them |
| O4 | The stack is Resource Manager ready and the existing pipeline is unaffected | `schema.yaml` covers every variable (pytest); `terraform fmt -check` + `validate` pass in a pinned container; the `iac` job is additive and lint/unit/e2e stay green |
