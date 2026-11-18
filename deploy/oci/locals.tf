# Always Free limits, fixed here and never exposed as variables (#279).
# Keep in step with free_tier_allowlist.yaml; re-check both each release (Oracle shrinks
# free limits silently: A1 went from 4 OCPU / 24 GB to 2 OCPU / 12 GB).

locals {
  # Compute: one Arm Ampere A1 instance using the whole free allowance.
  a1_shape     = "VM.Standard.A1.Flex"
  a1_ocpus     = 2
  a1_memory_gb = 12

  # Block storage: boot volume only, well inside the 200 GB free total.
  boot_volume_gb    = 100
  free_storage_gb   = 200
  free_a1_ocpus     = 2
  free_a1_memory_gb = 12

  # Autonomous Database: the Always Free instance, with vector search.
  adb_free_tier = true
  adb_version   = "26ai"
  adb_workload  = "OLTP"

  # Vault: the free shared (DEFAULT) vault with a software-protected key; no HSM.
  vault_type          = "DEFAULT"
  key_protection_mode = "SOFTWARE"

  # Network: 443 is the only port open to the internet.
  vcn_cidr    = "10.0.0.0/16"
  subnet_cidr = "10.0.1.0/24"
  https_port  = 443

  name = "zebra"

  # Billing guardrails (S2): budgets only alert, the quota is the hard stop. Budget amounts are
  # whole numbers in the tenancy's rate-card currency (1 GBP for a UK tenancy).
  budget_amount = 1
  budget_alerts = {
    actual-any   = { type = "ACTUAL", threshold_type = "ABSOLUTE", threshold = 0.01 }
    actual-50    = { type = "ACTUAL", threshold_type = "PERCENTAGE", threshold = 50 }
    actual-100   = { type = "ACTUAL", threshold_type = "PERCENTAGE", threshold = 100 }
    forecast-100 = { type = "FORECAST", threshold_type = "PERCENTAGE", threshold = 100 }
  }

  # Quota statements name the compartment by path from the root. The stack's compartment sits
  # directly under the tenancy when guardrails are on (precondition in guardrails.tf), so its
  # path is its name. Later statements override earlier ones in the same policy.
  quota_name = "${local.name}-always-free"
  quota_statements = [
    "zero compute-core quotas in compartment ${local.name}",
    "set compute-core quota standard-a1-core-count to ${local.free_a1_ocpus} in compartment ${local.name}",
    "zero compute-memory quotas in compartment ${local.name}",
    "set compute-memory quota standard-a1-memory-count to ${local.free_a1_memory_gb} in compartment ${local.name}",
    "zero database quotas in compartment ${local.name}",
    "set database quota adb-free-count to 1 in compartment ${local.name}",
    "zero load-balancer quotas in compartment ${local.name}",
    "set block-storage quota total-storage-gb to ${local.free_storage_gb} in compartment ${local.name}",
  ]

  freeform_tags = {
    "zebra-stack"   = "oci-provision"
    "zebra-channel" = var.release_channel
  }
}
