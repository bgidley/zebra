#!/usr/bin/env bash
# Shared helpers for the OKE migration scripts. Source this; do not execute.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OKE_DIR="$(cd "$HERE/.." && pwd)"
TF_DIR="$OKE_DIR/terraform"
K8S_DIR="$OKE_DIR/k8s"
SECRETS_DIR="$OKE_DIR/secrets"

log() { printf '\033[1;34m[oke]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[oke]\033[0m %s\n' "$*" >&2; }
die() {
  printf '\033[1;31m[oke] ERROR:\033[0m %s\n' "$*" >&2
  exit 1
}

require() { command -v "$1" >/dev/null 2>&1 || die "missing required tool: $1 (run scripts/00-bootstrap-tooling.sh)"; }

# Read a Terraform output (must have run `terraform apply`).
tf_out() { terraform -chdir="$TF_DIR" output -raw "$1" 2>/dev/null || die "terraform output '$1' unavailable — run 10-apply-infra.sh first"; }

# Registry host, e.g. lhr.ocir.io (strips the /<namespace> suffix).
ocir_host() { tf_out ocir_registry | cut -d/ -f1; }

# Log buildah/podman into OCIR. Requires registry.env (OCI_USERNAME / OCIR_TOKEN).
ocir_login() {
  local builder="${1:-buildah}"
  [ -f "$SECRETS_DIR/registry.env" ] || die "create $SECRETS_DIR/registry.env from registry.env.example"
  # shellcheck disable=SC1091
  source "$SECRETS_DIR/registry.env"
  : "${OCI_USERNAME:?OCI_USERNAME not set in registry.env}"
  : "${OCIR_TOKEN:?OCIR_TOKEN not set in registry.env}"
  echo "$OCIR_TOKEN" | "$builder" login --username "$OCI_USERNAME" --password-stdin "$(ocir_host)"
}
