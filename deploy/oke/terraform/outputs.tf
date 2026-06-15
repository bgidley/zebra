# ---------------------------------------------------------------------------
# Outputs consumed by the wrapper scripts (20-kubeconfig.sh, build/push, deploy).
# ---------------------------------------------------------------------------

output "cluster_id" {
  description = "OKE cluster OCID (used by `oci ce cluster create-kubeconfig`)."
  value       = oci_containerengine_cluster.this.id
}

output "cluster_name" {
  value = oci_containerengine_cluster.this.name
}

output "region" {
  value = var.region
}

output "ocir_namespace" {
  description = "Tenancy object-storage namespace (OCIR path segment)."
  value       = local.ocir_namespace
}

output "ocir_registry" {
  description = "OCIR registry host + namespace, e.g. lhr.ocir.io/<namespace>."
  value       = local.ocir_registry
}

output "image_web" {
  description = "Fully-qualified OCIR path for the web image (tag appended by build)."
  value       = "${local.ocir_registry}/${var.ocir_repo_prefix}/zebra-web"
}

output "image_claude" {
  value = "${local.ocir_registry}/${var.ocir_repo_prefix}/zebra-claude"
}

output "lb_subnet_id" {
  value = oci_core_subnet.lb.id
}
