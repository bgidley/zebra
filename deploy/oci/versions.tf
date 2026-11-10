# Zebra on OCI: a Resource Manager stack that stays inside Oracle's Always Free tier (#279).
#
# Only Always Free resources are created and no variable can pick a shape, size or service
# tier: those are fixed in locals.tf and re-asserted by preconditions. CI scans the plan
# against free_tier_allowlist.yaml (scripts/oci_plan_scan.py).

terraform {
  required_version = ">= 1.7.0"

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = ">= 6.0.0, < 8.0.0"
    }
  }
}

# Resource Manager authenticates the provider itself; region comes from the stack.
provider "oci" {
  region = var.region
}
