# Outputs carry identifiers only: never the wallet, passwords or secret contents (#279 O2).

output "compartment_id" {
  description = "The Zebra compartment."
  value       = oci_identity_compartment.zebra.id
}

output "instance_public_ip" {
  description = "Ephemeral public IP of the Zebra instance (changes if the instance is stopped and started)."
  value       = oci_core_instance.zebra.public_ip
}

output "zebra_url" {
  description = "Where Zebra will answer once first boot finishes."
  value       = var.domain != "" ? "https://${var.domain}/" : "https://${oci_core_instance.zebra.public_ip}/"
}

output "autonomous_database_id" {
  description = "The Always Free Autonomous Database."
  value       = oci_database_autonomous_database.zebra.id
}

output "vault_id" {
  description = "Vault holding the database admin password and, after first boot, Zebra's secrets."
  value       = oci_kms_vault.zebra.id
}

output "models_bucket" {
  description = "Object Storage bucket for the embedding model."
  value       = oci_objectstorage_bucket.models.name
}
