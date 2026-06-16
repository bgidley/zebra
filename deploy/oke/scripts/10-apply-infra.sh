#!/usr/bin/env bash
# Provision VCN + OKE + OCIR + IAM via Terraform. Idempotent; re-runnable.
set -euo pipefail
source "$(dirname "$0")/lib.sh"
require terraform

[ -f "$TF_DIR/terraform.tfvars" ] || die "create $TF_DIR/terraform.tfvars from terraform.tfvars.example"

terraform -chdir="$TF_DIR" init -input=false
terraform -chdir="$TF_DIR" validate
terraform -chdir="$TF_DIR" plan -input=false -out=tfplan

if [ "${AUTO_APPROVE:-0}" = "1" ]; then
  terraform -chdir="$TF_DIR" apply -input=false tfplan
else
  read -r -p "Apply this plan? [y/N] " ans
  [ "$ans" = "y" ] || die "aborted."
  terraform -chdir="$TF_DIR" apply -input=false tfplan
fi

log "infra applied. Cluster: $(tf_out cluster_name)  Registry: $(tf_out ocir_registry)"
