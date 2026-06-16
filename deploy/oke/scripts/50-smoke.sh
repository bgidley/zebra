#!/usr/bin/env bash
# Stand up an EPHEMERAL smoke instance (own Oracle schema), run the smoke suite
# against it, and tear it down. Prod is never touched. Usage: 50-smoke.sh <tag>
set -euo pipefail
source "$(dirname "$0")/lib.sh"
require kubectl
require kustomize

TAG="${1:?usage: 50-smoke.sh <image-tag>}"
PROJECT_ROOT="$(cd "$OKE_DIR/../.." && pwd)"
REGISTRY="$(tf_out ocir_registry)"
PREFIX="${OCIR_REPO_PREFIX:-zebra}"
WEB="$REGISTRY/$PREFIX/zebra-web"
: "${SMOKE_PASSWORD:?set SMOKE_PASSWORD (also present in secrets/smoke.env if used)}"

PF_PID=""
cleanup() {
  [ -n "$PF_PID" ] && kill "$PF_PID" 2>/dev/null || true
  log "tearing down namespace smoke"
  kubectl delete ns smoke --ignore-not-found --wait=false
}
trap cleanup EXIT

log "creating ephemeral namespace smoke"
kubectl create ns smoke --dry-run=client -o yaml | kubectl apply -f -

# Secrets for the smoke instance (pull + smoke Oracle schema).
# shellcheck disable=SC1091
source "$SECRETS_DIR/registry.env"
kubectl -n smoke create secret docker-registry ocir-pull \
  --docker-server="$(ocir_host)" --docker-username="$OCI_USERNAME" \
  --docker-password="$OCIR_TOKEN" --docker-email="$OCI_EMAIL" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n smoke create secret generic zebra-smoke-secrets \
  --from-env-file="$SECRETS_DIR/smoke.env" \
  --dry-run=client -o yaml | kubectl apply -f -

log "deploying smoke instance at $WEB:$TAG"
( cd "$K8S_DIR/overlays/smoke" && kustomize edit set image "zebra-web=$WEB:$TAG" )
kustomize build "$K8S_DIR/overlays/smoke" | kubectl apply -f -
git -C "$OKE_DIR" checkout -- k8s/overlays/smoke 2>/dev/null || true

kubectl -n smoke rollout status deploy/zebra-web --timeout=180s

log "provisioning smoke user"
POD="$(kubectl -n smoke get pod -l app=zebra-web -o jsonpath='{.items[0].metadata.name}')"
kubectl -n smoke exec "$POD" -- \
  python zebra-agent-web/manage.py ensure_smoke_user "$SMOKE_PASSWORD"

log "port-forwarding smoke service → localhost:18000"
kubectl -n smoke port-forward svc/zebra-web 18000:80 >/dev/null 2>&1 &
PF_PID=$!
timeout 60 sh -c 'until curl -sf http://localhost:18000/api/health/ >/dev/null; do sleep 2; done'

log "running smoke suite"
( cd "$PROJECT_ROOT" \
  && SMOKE_BASE_URL="http://localhost:18000" SMOKE_USERNAME="smoke" SMOKE_PASSWORD="$SMOKE_PASSWORD" \
     uv run pytest zebra-agent-web/tests/smoke/ -v -m smoke )

log "smoke passed."
