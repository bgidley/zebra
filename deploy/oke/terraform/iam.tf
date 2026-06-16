# ---------------------------------------------------------------------------
# IAM for OKE: a dynamic group of the worker instances + policies allowing them
# to pull from OCIR, and allowing the OKE service to manage load balancers.
#
# Dynamic groups and policies live in the ROOT (tenancy) compartment, so the
# Terraform user needs tenancy-level manage permissions for these. The
# onboarding guide documents the bootstrap policy required.
# ---------------------------------------------------------------------------

resource "oci_identity_dynamic_group" "oke_nodes" {
  compartment_id = var.tenancy_ocid
  name           = "${local.name}-oke-nodes"
  description    = "Zebra OKE worker node instances"
  matching_rule  = "ALL {instance.compartment.id = '${var.compartment_ocid}'}"
}

resource "oci_identity_policy" "oke" {
  compartment_id = var.tenancy_ocid
  name           = "${local.name}-oke-policy"
  description    = "Zebra OKE: node OCIR pulls + service LB management"

  statements = [
    # Worker nodes pull private images from OCIR in the compartment.
    "Allow dynamic-group ${oci_identity_dynamic_group.oke_nodes.name} to read repos in compartment id ${var.compartment_ocid}",
    # OKE service manages networking/load-balancers for type=LoadBalancer Services.
    "Allow service OKE to manage cluster-node-pools in compartment id ${var.compartment_ocid}",
    "Allow service OKE to manage virtual-network-family in compartment id ${var.compartment_ocid}",
    "Allow service OKE to manage load-balancers in compartment id ${var.compartment_ocid}",
  ]
}
