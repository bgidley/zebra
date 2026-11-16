## MODIFIED Requirements

### Requirement: No variable reaches a paid resource
The stack's variables SHALL be limited to tenancy, region (default `uk-london-1`), parent
compartment, optional SSH public key, optional domain, release channel, `create_guardrails` and
`alert_email`. Shape, size, database tier, vault type, key protection mode, budget amounts,
alert thresholds and quota statements SHALL be fixed in the configuration. An SSH key SHALL NOT
open port 22. Every variable SHALL appear in `schema.yaml`.

#### Scenario: New variable
- **WHEN** a variable is added to the stack
- **THEN** the `tests/iac` variable check fails until the change is reviewed and the list updated

#### Scenario: SSH key given
- **WHEN** `ssh_public_key` is set
- **THEN** it is installed in the instance metadata and the security list still opens only 443

### Requirement: Plan scan against the Always Free allowlist
`scripts/oci_plan_scan.py` SHALL read `terraform show -json` output and fail (exit 1) when a
managed resource is not on `deploy/oci/free_tier_allowlist.yaml`, breaks its type's `max_count`,
`require`, `max`, `one_of` or `nonempty` rule, leaves a required value unknown at plan time,
when an instance's boot-volume size is unknown at plan time, or when the plan's total A1 OCPU,
A1 memory or block storage exceeds the limits. It SHALL exit 0 on a clean plan and 2 on
unreadable input.

#### Scenario: Bad plan per rule
- **WHEN** a plan has an unlisted type, a paid shape, more than 2 OCPU or 12 GB, a second
  instance or ADB, over 200 GB of storage, `is_free_tier` false or unknown, a non-DEFAULT vault,
  an HSM key, a reserved IP, a load balancer, NAT gateway or DRG, or an Archive bucket
- **THEN** the scan fails and names the resource and rule

#### Scenario: Unknown boot-volume size
- **WHEN** an instance's `boot_volume_size_in_gbs` is known only after apply
- **THEN** the scan fails instead of assuming the 47 GB default

#### Scenario: Real plan
- **WHEN** the stack's own plan is scanned
- **THEN** the scan passes

### Requirement: CI checks the stack without credentials
The `iac` CI job SHALL run `scripts/oci_iac_check.sh`, which first proves `terraform fmt -check`
rejects a mis-formatted fixture with a diff, then runs `terraform fmt -check` on the stack
(printing the diff on failure), `init`, `validate`, `terraform test` with a mocked `oci`
provider, and a plan with throwaway credentials followed by the plan scan, in a pinned Terraform
container. It SHALL need no OCI credentials and SHALL never apply.

#### Scenario: Pipeline
- **WHEN** a pipeline runs
- **THEN** the `iac` job passes without any OCI credential variables and creates nothing in any
  tenancy

#### Scenario: Mis-formatted stack
- **WHEN** a file under `deploy/oci/` is not `terraform fmt` clean
- **THEN** the job fails and prints the fmt diff
