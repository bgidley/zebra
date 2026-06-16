# ---------------------------------------------------------------------------
# Provider & global configuration for the Zebra OKE migration.
#
# Nothing here is applied automatically. Run via deploy/oke/scripts/10-apply-infra.sh
# (or `make infra` from deploy/oke) after filling terraform.tfvars from the
# onboarding guide (deploy/oke/docs/oci-onboarding.md).
# ---------------------------------------------------------------------------

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = ">= 5.30.0"
    }
  }

  # State is local by default (git-ignored). For team use, switch to an OCI
  # Object Storage backend — see deploy/oke/README.md.
}

provider "oci" {
  tenancy_ocid     = var.tenancy_ocid
  user_ocid        = var.user_ocid
  fingerprint      = var.fingerprint
  private_key_path = var.private_key_path
  region           = var.region
}

# OCIR namespace is the tenancy object-storage namespace; needed to tag/push images.
data "oci_objectstorage_namespace" "this" {
  compartment_id = var.tenancy_ocid
}

# All availability domains in the tenancy; we place the node pool in the first.
data "oci_identity_availability_domains" "ads" {
  compartment_id = var.tenancy_ocid
}

locals {
  name           = var.cluster_name
  ocir_namespace = data.oci_objectstorage_namespace.this.namespace
  # e.g. lhr.ocir.io/<namespace>
  ocir_registry = "${var.region_key}.ocir.io/${data.oci_objectstorage_namespace.this.namespace}"
}
