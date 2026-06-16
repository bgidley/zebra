#!/usr/bin/env bash
# Create namespaces + k8s Secrets from local env files (never committed).
# Idempotent (apply-style). Populate deploy/oke/secrets/*.env from the .example files.
set -euo pipefail
source "$(dirname "$0")/lib.sh"
require kubectl

# --- namespaces ---
kubectl apply -f "$K8S_DIR/base/namespaces.yaml"

# --- OCIR image-pull secret (prod + tools; smoke gets its own in 50-smoke.sh) ---
[ -f "$SECRETS_DIR/registry.env" ] || die "create $SECRETS_DIR/registry.env from registry.env.example"
# shellcheck disable=SC1091
source "$SECRETS_DIR/registry.env"
: "${OCI_USERNAME:?}" "${OCIR_TOKEN:?}" "${OCI_EMAIL:?}"
REG_HOST="$(ocir_host)"

mk_pull_secret() {
  local ns="$1"
  kubectl -n "$ns" create secret docker-registry ocir-pull \
    --docker-server="$REG_HOST" \
    --docker-username="$OCI_USERNAME" \
    --docker-password="$OCIR_TOKEN" \
    --docker-email="$OCI_EMAIL" \
    --dry-run=client -o yaml | kubectl apply -f -
}

mk_generic() {
  local ns="$1" name="$2" envfile="$3"
  [ -f "$envfile" ] || die "missing $envfile (copy from ${envfile}.example)"
  kubectl -n "$ns" create secret generic "$name" \
    --from-env-file="$envfile" \
    --dry-run=client -o yaml | kubectl apply -f -
}

mk_pull_secret prod
mk_pull_secret tools

# --- app secrets ---
mk_generic prod zebra-prod-secrets "$SECRETS_DIR/prod.env"
mk_generic tools claude-secrets "$SECRETS_DIR/claude.env"

log "secrets created in namespaces: prod, tools."
log "(smoke secret + pull secret are created per-run by 50-smoke.sh)"
