# ---------------------------------------------------------------------------
# VCN + public subnets for a free-tier-friendly OKE cluster.
#
# Design choices (cost/free-tier):
#   - Workers live in a PUBLIC subnet behind an Internet Gateway, so we avoid a
#     paid NAT Gateway for egress (image pulls, Anthropic, Oracle ADB).
#   - A Service Gateway gives free private access to OCI services (OCIR, etc.).
#   - Ingress is locked down with security lists; the k8s API and SSH are
#     restricted to var.admin_cidr.
# ---------------------------------------------------------------------------

resource "oci_core_vcn" "this" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = [var.vcn_cidr]
  display_name   = "${local.name}-vcn"
  dns_label      = "zebravcn"
}

resource "oci_core_internet_gateway" "this" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.this.id
  display_name   = "${local.name}-igw"
  enabled        = true
}

data "oci_core_services" "all" {
  filter {
    name   = "name"
    values = ["All .* Services In Oracle Services Network"]
    regex  = true
  }
}

resource "oci_core_service_gateway" "this" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.this.id
  display_name   = "${local.name}-sgw"
  services {
    service_id = data.oci_core_services.all.services[0]["id"]
  }
}

resource "oci_core_route_table" "public" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.this.id
  display_name   = "${local.name}-public-rt"

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.this.id
  }

  route_rules {
    destination       = data.oci_core_services.all.services[0]["cidr_block"]
    destination_type  = "SERVICE_CIDR_BLOCK"
    network_entity_id = oci_core_service_gateway.this.id
  }
}

# --- Node subnet -----------------------------------------------------------
resource "oci_core_security_list" "nodes" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.this.id
  display_name   = "${local.name}-nodes-sl"

  # Egress: anywhere (IGW) — pulls, Anthropic, Oracle ADB.
  egress_security_rules {
    destination = "0.0.0.0/0"
    protocol    = "all"
  }

  # Node-to-node (same subnet) — all traffic.
  ingress_security_rules {
    source   = var.vcn_cidr
    protocol = "all"
  }

  # Control-plane -> workers (Flannel/OKE management).
  ingress_security_rules {
    source   = var.admin_cidr
    protocol = "6" # TCP
    tcp_options {
      min = 22
      max = 22
    }
  }

  # NodePort range from the LB subnet (service LoadBalancer health + traffic).
  ingress_security_rules {
    source   = var.vcn_cidr
    protocol = "6" # TCP
    tcp_options {
      min = 30000
      max = 32767
    }
  }

  # Path-MTU discovery.
  ingress_security_rules {
    source   = "0.0.0.0/0"
    protocol = "1" # ICMP
    icmp_options {
      type = 3
      code = 4
    }
  }
}

resource "oci_core_subnet" "nodes" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.this.id
  cidr_block                 = cidrsubnet(var.vcn_cidr, 8, 1) # 10.20.1.0/24
  display_name               = "${local.name}-nodes"
  dns_label                  = "nodes"
  route_table_id             = oci_core_route_table.public.id
  security_list_ids          = [oci_core_security_list.nodes.id]
  prohibit_public_ip_on_vnic = false
}

# --- Kubernetes API endpoint subnet ---------------------------------------
resource "oci_core_security_list" "k8s_api" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.this.id
  display_name   = "${local.name}-k8sapi-sl"

  egress_security_rules {
    destination = "0.0.0.0/0"
    protocol    = "all"
  }

  # kubectl access from admin.
  ingress_security_rules {
    source   = var.admin_cidr
    protocol = "6"
    tcp_options {
      min = 6443
      max = 6443
    }
  }

  # Worker nodes -> control plane.
  ingress_security_rules {
    source   = oci_core_subnet.nodes.cidr_block
    protocol = "6"
    tcp_options {
      min = 6443
      max = 6443
    }
  }

  ingress_security_rules {
    source   = oci_core_subnet.nodes.cidr_block
    protocol = "6"
    tcp_options {
      min = 12250
      max = 12250
    }
  }
}

resource "oci_core_subnet" "k8s_api" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.this.id
  cidr_block                 = cidrsubnet(var.vcn_cidr, 8, 2) # 10.20.2.0/24
  display_name               = "${local.name}-k8sapi"
  dns_label                  = "k8sapi"
  route_table_id             = oci_core_route_table.public.id
  security_list_ids          = [oci_core_security_list.k8s_api.id]
  prohibit_public_ip_on_vnic = false
}

# --- Load-balancer subnet --------------------------------------------------
resource "oci_core_security_list" "lb" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.this.id
  display_name   = "${local.name}-lb-sl"

  egress_security_rules {
    destination = "0.0.0.0/0"
    protocol    = "all"
  }

  # Public HTTP/HTTPS to the prod app.
  ingress_security_rules {
    source   = "0.0.0.0/0"
    protocol = "6"
    tcp_options {
      min = 80
      max = 80
    }
  }

  ingress_security_rules {
    source   = "0.0.0.0/0"
    protocol = "6"
    tcp_options {
      min = 443
      max = 443
    }
  }
}

resource "oci_core_subnet" "lb" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.this.id
  cidr_block                 = cidrsubnet(var.vcn_cidr, 8, 3) # 10.20.3.0/24
  display_name               = "${local.name}-lb"
  dns_label                  = "lb"
  route_table_id             = oci_core_route_table.public.id
  security_list_ids          = [oci_core_security_list.lb.id]
  prohibit_public_ip_on_vnic = false
}
