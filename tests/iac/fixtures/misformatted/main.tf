# Deliberately mis-formatted (#299): scripts/oci_iac_check.sh checks that `terraform fmt -check`
# rejects this file and prints its diff, so a gate that silently passes is caught.
locals {
  name = "zebra"
  boot_volume_gb    = 100
}
