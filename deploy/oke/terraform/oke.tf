# ---------------------------------------------------------------------------
# OKE Basic cluster (free control plane) + a single Always-Free-shaped A1 node pool.
# CNI: Flannel overlay (fewer IPs, free). Public API endpoint locked to admin_cidr.
# ---------------------------------------------------------------------------

resource "oci_containerengine_cluster" "this" {
  compartment_id     = var.compartment_ocid
  name               = local.name
  kubernetes_version = var.kubernetes_version
  vcn_id             = oci_core_vcn.this.id
  type               = "BASIC_CLUSTER"

  cluster_pod_network_options {
    cni_type = "FLANNEL_OVERLAY"
  }

  endpoint_config {
    subnet_id            = oci_core_subnet.k8s_api.id
    is_public_ip_enabled = true
  }

  options {
    service_lb_subnet_ids = [oci_core_subnet.lb.id]
    add_ons {
      is_kubernetes_dashboard_enabled = false
      is_tiller_enabled               = false
    }
  }
}

# Best-effort lookup of the newest aarch64 OKE image for this k8s version.
# Override with var.node_image_ocid if the heuristic picks the wrong one.
data "oci_containerengine_node_pool_option" "this" {
  node_pool_option_id = "all"
  compartment_id      = var.compartment_ocid
}

locals {
  _ver_no_v = replace(var.kubernetes_version, "v", "")
  _arm_images = [
    for s in data.oci_containerengine_node_pool_option.this.sources :
    s if can(regex("aarch64", s.source_name)) && can(regex(local._ver_no_v, s.source_name))
  ]
  node_image_ocid = var.node_image_ocid != "" ? var.node_image_ocid : local._arm_images[0].image_id
}

resource "oci_containerengine_node_pool" "this" {
  cluster_id         = oci_containerengine_cluster.this.id
  compartment_id     = var.compartment_ocid
  kubernetes_version = var.kubernetes_version
  name               = "${local.name}-np"
  node_shape         = "VM.Standard.A1.Flex"

  node_shape_config {
    ocpus         = var.node_ocpus
    memory_in_gbs = var.node_memory_gb
  }

  node_config_details {
    size = var.node_count

    placement_configs {
      availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
      subnet_id           = oci_core_subnet.nodes.id
    }

    node_pool_pod_network_option_details {
      cni_type = "FLANNEL_OVERLAY"
    }
  }

  node_source_details {
    source_type = "IMAGE"
    image_id    = local.node_image_ocid
  }

  ssh_public_key = var.ssh_public_key

  # SSH key / image changes recreate nodes; tolerate drift on the auto-picked image.
  lifecycle {
    ignore_changes = [node_source_details[0].image_id]
  }
}
