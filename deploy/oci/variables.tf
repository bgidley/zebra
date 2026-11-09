# Stack variables. Deliberately none of them selects a shape, size, count or service tier:
# those live in locals.tf so a user cannot reach a paid resource from the Resource Manager form.
# Every variable here must also appear in schema.yaml (tests/iac checks this).

variable "tenancy_ocid" {
  description = "Tenancy OCID (filled in by Resource Manager)."
  type        = string
}

variable "region" {
  description = "Region to deploy into. Must be the tenancy home region for the Always Free database."
  type        = string
  default     = "uk-london-1"
}

variable "compartment_ocid" {
  description = "Parent compartment for the new Zebra compartment (Resource Manager fills in the stack's compartment)."
  type        = string
}

variable "ssh_public_key" {
  description = "Optional SSH public key for the opc user. Port 22 stays closed either way."
  type        = string
  default     = ""

  validation {
    condition     = var.ssh_public_key == "" || can(regex("^(ssh-(ed25519|rsa)|ecdsa-sha2-nistp(256|384|521)) ", var.ssh_public_key))
    error_message = "ssh_public_key must be empty or an OpenSSH public key."
  }
}

variable "domain" {
  description = "Optional DNS name for the instance. Empty means a hostname derived from the public IP."
  type        = string
  default     = ""

  validation {
    condition     = var.domain == "" || can(regex("^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\\.)+[a-z]{2,}$", lower(var.domain)))
    error_message = "domain must be empty or a DNS name such as zebra.example.com."
  }
}

variable "release_channel" {
  description = "Zebra release channel the instance follows."
  type        = string
  default     = "stable"

  validation {
    condition     = contains(["stable", "beta"], var.release_channel)
    error_message = "release_channel must be stable or beta."
  }
}
