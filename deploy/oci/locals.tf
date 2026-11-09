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

  freeform_tags = {
    "zebra-stack"   = "oci-provision"
    "zebra-channel" = var.release_channel
  }
}
