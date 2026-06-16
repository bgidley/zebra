# ---------------------------------------------------------------------------
# Inputs. Copy terraform.tfvars.example -> terraform.tfvars and fill in.
# The onboarding guide (docs/oci-onboarding.md) explains where each value comes from.
# ---------------------------------------------------------------------------

# --- OCI auth (from `oci setup config` / onboarding) -----------------------
variable "tenancy_ocid" {
  type        = string
  description = "Tenancy OCID (ocid1.tenancy...)."
}

variable "user_ocid" {
  type        = string
  description = "IAM user OCID used by Terraform (ocid1.user...)."
}

variable "fingerprint" {
  type        = string
  description = "API signing key fingerprint."
}

variable "private_key_path" {
  type        = string
  description = "Path to the API signing private key PEM (e.g. ~/.oci/oci_api_key.pem)."
}

variable "region" {
  type        = string
  description = "OCI region identifier, e.g. uk-london-1."
}

variable "region_key" {
  type        = string
  description = "Three-letter OCIR region key for the registry host, e.g. lhr for uk-london-1."
}

# --- Placement -------------------------------------------------------------
variable "compartment_ocid" {
  type        = string
  description = "Compartment that holds all Zebra resources (create a dedicated 'zebra' compartment)."
}

# --- Cluster ---------------------------------------------------------------
variable "cluster_name" {
  type    = string
  default = "zebra"
}

variable "kubernetes_version" {
  type        = string
  description = "OKE Kubernetes version, e.g. v1.30.1. List options: `oci ce cluster-options get --cluster-option-id all`."
  default     = "v1.30.1"
}

# Worker pool sizing. Free Always-Free A1 pool is 4 OCPU / 24 GB total.
# Start small for the parallel-run migration week, scale to 4/24 at cutover.
variable "node_ocpus" {
  type    = number
  default = 2
}

variable "node_memory_gb" {
  type    = number
  default = 12
}

variable "node_count" {
  type    = number
  default = 1
}

variable "node_image_ocid" {
  type        = string
  description = "Override OKE node image OCID. Leave empty to auto-pick the latest aarch64 image for kubernetes_version."
  default     = ""
}

variable "ssh_public_key" {
  type        = string
  description = "SSH public key contents for node access."
}

# --- Networking ------------------------------------------------------------
variable "vcn_cidr" {
  type    = string
  default = "10.20.0.0/16"
}

variable "admin_cidr" {
  type        = string
  description = "CIDR allowed to reach the public Kubernetes API endpoint and node SSH. Use your admin IP /32."
  default     = "0.0.0.0/0"
}

variable "app_port" {
  type        = number
  description = "Container port the LB forwards to (Daphne)."
  default     = 8000
}

# --- Registry --------------------------------------------------------------
variable "ocir_repo_prefix" {
  type        = string
  description = "Prefix for OCIR repositories, e.g. 'zebra' -> zebra/zebra-web."
  default     = "zebra"
}
