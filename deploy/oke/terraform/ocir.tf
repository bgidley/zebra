# ---------------------------------------------------------------------------
# OCIR private repositories for the two images.
#
# Note on retention: OCIR image-retention policies are not exposed as a stable
# Terraform resource, so registry hygiene (keep last N) is handled by
# deploy/oke/scripts/lib.sh::prune_ocir (invoked from the CI deploy stage)
# rather than here. See README.md.
# ---------------------------------------------------------------------------

resource "oci_artifacts_container_repository" "web" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.ocir_repo_prefix}/zebra-web"
  is_public      = false
}

resource "oci_artifacts_container_repository" "claude" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.ocir_repo_prefix}/zebra-claude"
  is_public      = false
}
