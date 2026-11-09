# Everything Zebra needs, in one compartment, all Always Free.
#
# Lookups (availability domain, image, Object Storage namespace) are keyed on the new
# compartment, so they are read at apply time. A plan therefore needs no OCI API calls,
# which is what lets CI render and scan it without credentials.

resource "oci_identity_compartment" "zebra" {
  compartment_id = var.compartment_ocid
  name           = local.name
  description    = "Zebra (Always Free) - created by the Zebra Resource Manager stack"
  enable_delete  = true
  freeform_tags  = local.freeform_tags
}

data "oci_identity_availability_domains" "ads" {
  compartment_id = oci_identity_compartment.zebra.id
}

data "oci_core_images" "oracle_linux" {
  compartment_id           = oci_identity_compartment.zebra.id
  operating_system         = "Oracle Linux"
  operating_system_version = "9"
  shape                    = local.a1_shape
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

data "oci_objectstorage_namespace" "ns" {
  compartment_id = oci_identity_compartment.zebra.id
}

# --- Network: one public subnet, HTTPS in, everything out. No NAT, no DRG, no LB. ---

resource "oci_core_vcn" "zebra" {
  compartment_id = oci_identity_compartment.zebra.id
  cidr_blocks    = [local.vcn_cidr]
  display_name   = "${local.name}-vcn"
  dns_label      = local.name
  freeform_tags  = local.freeform_tags
}

resource "oci_core_internet_gateway" "zebra" {
  compartment_id = oci_identity_compartment.zebra.id
  vcn_id         = oci_core_vcn.zebra.id
  display_name   = "${local.name}-igw"
  enabled        = true
  freeform_tags  = local.freeform_tags
}

resource "oci_core_route_table" "zebra" {
  compartment_id = oci_identity_compartment.zebra.id
  vcn_id         = oci_core_vcn.zebra.id
  display_name   = "${local.name}-rt"
  freeform_tags  = local.freeform_tags

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.zebra.id
  }
}

resource "oci_core_security_list" "zebra" {
  compartment_id = oci_identity_compartment.zebra.id
  vcn_id         = oci_core_vcn.zebra.id
  display_name   = "${local.name}-https-only"
  freeform_tags  = local.freeform_tags

  egress_security_rules {
    destination = "0.0.0.0/0"
    protocol    = "all"
  }

  ingress_security_rules {
    source   = "0.0.0.0/0"
    protocol = "6" # TCP
    tcp_options {
      min = local.https_port
      max = local.https_port
    }
  }
}

resource "oci_core_subnet" "zebra" {
  compartment_id             = oci_identity_compartment.zebra.id
  vcn_id                     = oci_core_vcn.zebra.id
  cidr_block                 = local.subnet_cidr
  display_name               = "${local.name}-public"
  dns_label                  = "pub"
  route_table_id             = oci_core_route_table.zebra.id
  security_list_ids          = [oci_core_security_list.zebra.id]
  prohibit_public_ip_on_vnic = false
  freeform_tags              = local.freeform_tags
}

# --- Compute: one Arm A1 instance with an ephemeral public IP (no reserved IP). ---

resource "oci_core_instance" "zebra" {
  compartment_id      = oci_identity_compartment.zebra.id
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  display_name        = local.name
  shape               = local.a1_shape
  freeform_tags       = local.freeform_tags

  shape_config {
    ocpus         = local.a1_ocpus
    memory_in_gbs = local.a1_memory_gb
  }

  source_details {
    source_type             = "image"
    source_id               = data.oci_core_images.oracle_linux.images[0].id
    boot_volume_size_in_gbs = local.boot_volume_gb
  }

  # assign_public_ip gives the VNIC an ephemeral public IP, which is free; a reserved IP
  # may bill while unattached, so the stack never creates one.
  create_vnic_details {
    subnet_id        = oci_core_subnet.zebra.id
    assign_public_ip = "true"
    hostname_label   = local.name
  }

  metadata = var.ssh_public_key == "" ? {} : { ssh_authorized_keys = var.ssh_public_key }

  lifecycle {
    precondition {
      condition     = local.a1_shape == "VM.Standard.A1.Flex"
      error_message = "Only the Always Free Arm shape VM.Standard.A1.Flex is allowed."
    }
    precondition {
      condition     = local.a1_ocpus <= local.free_a1_ocpus && local.a1_memory_gb <= local.free_a1_memory_gb
      error_message = "The A1 instance must stay within the Always Free 2 OCPU / 12 GB."
    }
    precondition {
      condition     = local.boot_volume_gb <= local.free_storage_gb
      error_message = "Block storage must stay within the Always Free 200 GB."
    }
  }
}

# --- Vault: the free DEFAULT vault, a software key, and the database admin password. ---

resource "oci_kms_vault" "zebra" {
  compartment_id = oci_identity_compartment.zebra.id
  display_name   = "${local.name}-vault"
  vault_type     = local.vault_type
  freeform_tags  = local.freeform_tags

  lifecycle {
    precondition {
      condition     = local.vault_type == "DEFAULT"
      error_message = "Only the free DEFAULT (shared) vault is allowed; a VIRTUAL_PRIVATE vault bills."
    }
  }
}

resource "oci_kms_key" "zebra" {
  compartment_id      = oci_identity_compartment.zebra.id
  display_name        = "${local.name}-key"
  management_endpoint = oci_kms_vault.zebra.management_endpoint
  protection_mode     = local.key_protection_mode
  freeform_tags       = local.freeform_tags

  key_shape {
    algorithm = "AES"
    length    = 32
  }

  lifecycle {
    precondition {
      condition     = local.key_protection_mode == "SOFTWARE"
      error_message = "Only software-protected keys are free; HSM keys bill."
    }
  }
}

# Vault generates the password itself, so it never appears in configuration or outputs.
resource "oci_vault_secret" "adb_admin" {
  compartment_id         = oci_identity_compartment.zebra.id
  vault_id               = oci_kms_vault.zebra.id
  key_id                 = oci_kms_key.zebra.id
  secret_name            = "${local.name}-adb-admin"
  description            = "Autonomous Database ADMIN password (generated by Vault)"
  enable_auto_generation = true
  freeform_tags          = local.freeform_tags

  secret_generation_context {
    generation_type     = "PASSPHRASE"
    generation_template = "DBAAS_DEFAULT_PASSWORD"
    passphrase_length   = 32
  }
}

# --- Database: the Always Free Autonomous Database. It cannot sit in a VCN, so it has a public
# endpoint with mTLS required and an access list holding only the instance's public IP. ---

resource "oci_database_autonomous_database" "zebra" {
  compartment_id              = oci_identity_compartment.zebra.id
  db_name                     = local.name
  display_name                = "${local.name}-adb"
  db_workload                 = local.adb_workload
  db_version                  = local.adb_version
  is_free_tier                = local.adb_free_tier
  is_mtls_connection_required = true
  whitelisted_ips             = [oci_core_instance.zebra.public_ip]
  secret_id                   = oci_vault_secret.adb_admin.id
  secret_version_number       = 1
  freeform_tags               = local.freeform_tags

  lifecycle {
    precondition {
      condition     = local.adb_free_tier
      error_message = "The Autonomous Database must be the Always Free instance (is_free_tier = true)."
    }
  }
}

# --- Object Storage: the bucket the in-database embedding model is loaded from. ---

resource "oci_objectstorage_bucket" "models" {
  compartment_id = oci_identity_compartment.zebra.id
  namespace      = data.oci_objectstorage_namespace.ns.namespace
  name           = "zebra-models"
  access_type    = "NoPublicAccess"
  storage_tier   = "Standard"
  versioning     = "Disabled"
  freeform_tags  = local.freeform_tags
}
