## Context

#279 slice S1 (plan: onboarding build plan, section 1). Decisions (2026-11-09): London
`uk-london-1`; one Arm A1 instance at 2 OCPU / 12 GB (Oracle cut the free A1 allowance from
4 / 24); the Always Free ADB on a public endpoint with mTLS and an IP access list (a free ADB
cannot have a private endpoint); ephemeral public IP, no reserved IP.

## Goals / Non-Goals

**Goals:** a stack that can only create Always Free resources, with a CI check that needs no
credentials. **Non-goals:** cloud-init / first boot (S3), budgets and quotas (S2), TLS and setup
token (S4), release zip and image digest (#283), applying to any tenancy.

## Decisions

- **Limits are locals, not variables.** The Resource Manager form cannot offer a paid choice
  because there is none. `precondition`s on the instance, vault, key and ADB restate the limits,
  so a later edit that raises a local fails at plan time with a plain message.
- **Plan without credentials.** The availability-domain, image and Object Storage namespace
  lookups take the new compartment's id, which is unknown at plan time, so Terraform defers them
  to apply. A plan then makes no API calls, and a throwaway API key (generated per run, never
  valid) is enough for the provider to configure. This gives a real `terraform show -json` plan
  to scan, which `terraform test` cannot export.
- **Two layers of test.** `terraform test` with `mock_provider "oci"` checks the stack's intent
  (shape, sizes, mTLS, 443 only, SSH key never opens 22, variable validation). The plan scan
  checks the rendered plan against `free_tier_allowlist.yaml`, so a new resource type cannot
  slip in unreviewed. Pytest feeds the scanner the real plan (trimmed fixture) and one bad plan
  per rule.
- **Allowlist is data.** Per type: `max_count`, `require` (exact value, known at plan time),
  `max`; plan totals for A1 OCPU, A1 memory and block storage (boot volumes default to 47 GB).
  Named `denied` types (LB, NLB, NAT, DRG) only improve the message.
- **ADB admin password from Vault** (`enable_auto_generation`, `DBAAS_DEFAULT_PASSWORD`), passed
  as `secret_id`: no password in variables, config or outputs. Outputs are ids, IP and URL only.
- **Terraform in a container** (`docker.io/hashicorp/terraform:1.12.2`, provider cache in
  `~/.cache/zebra-terraform-plugins`); nothing installed on the host. The lock file carries
  arm64 and amd64 hashes (Resource Manager runs amd64).

## Risks / Trade-offs

- `db_version = "26ai"` and the ADB reading its admin password from a Vault secret (it may
  need an IAM policy for the database service) are unverified until the S3 tenancy test.
- Plan-time lookups deferred to apply mean a missing A1 image or capacity surfaces only on
  apply (S3/S5 handle retry).
- The public ADB is reachable only with the wallet and from the instance IP; that IP changes on
  stop/start (S4/S5).
- Oracle shrinks free limits silently: the allowlist records the date it was checked and #283
  re-runs the scan per release.
