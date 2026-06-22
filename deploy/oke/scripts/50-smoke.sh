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
: "${SMOKE_PASSWORD:?set SMOKE_PASSWORD}"
: "${ANTHROPIC_API_KEY:?set ANTHROPIC_API_KEY}"

# Ephemeral Oracle schema per run (mirrors the e2e job — real prod parity, fully
# isolated, no shared schema to collide on). Provisioner creds come from a
# secret-volume mount (kept out of GitLab CI/CD variables); fall back to env
# vars already set for local/operator use.
PROVISIONER_DIR="/etc/gitlab-secrets/e2e-provisioner"
if [ -z "${E2E_PROVISIONER_DSN:-}" ] && [ -d "$PROVISIONER_DIR" ]; then
  E2E_PROVISIONER_DSN="$(cat "$PROVISIONER_DIR/E2E_PROVISIONER_DSN")"
  E2E_PROVISIONER_USERNAME="$(cat "$PROVISIONER_DIR/E2E_PROVISIONER_USERNAME")"
  E2E_PROVISIONER_PASSWORD="$(cat "$PROVISIONER_DIR/E2E_PROVISIONER_PASSWORD")"
  export E2E_PROVISIONER_DSN E2E_PROVISIONER_USERNAME E2E_PROVISIONER_PASSWORD
fi
: "${E2E_PROVISIONER_DSN:?set E2E_PROVISIONER_DSN}"
: "${E2E_PROVISIONER_USERNAME:?set E2E_PROVISIONER_USERNAME}"
: "${E2E_PROVISIONER_PASSWORD:?set E2E_PROVISIONER_PASSWORD}"

SMOKE_SCHEMA="E2E_SMOKE_${CI_PIPELINE_ID:-$$}"
export E2E_SCHEMA_PASSWORD="Az9$(openssl rand -hex 13)"
DJANGO_SECRET_KEY="$(openssl rand -hex 32)"

PF_PID=""
cleanup() {
  [ -n "$PF_PID" ] && kill "$PF_PID" 2>/dev/null || true
  log "tearing down namespace smoke"
  kubectl delete ns smoke --ignore-not-found --wait=false
  log "dropping ephemeral schema $SMOKE_SCHEMA"
  ( cd "$PROJECT_ROOT" && uv run python scripts/e2e_oracle_schema.py drop --schema "$SMOKE_SCHEMA" ) || true
}
trap cleanup EXIT

log "provisioning ephemeral Oracle schema $SMOKE_SCHEMA"
( cd "$PROJECT_ROOT" && uv run python scripts/e2e_oracle_schema.py create --schema "$SMOKE_SCHEMA" )

log "creating ephemeral namespace smoke"
kubectl create ns smoke --dry-run=client -o yaml | kubectl apply -f -

# Secrets for the smoke instance (pull + smoke Oracle schema). On an ephemeral CI
# runner there's no secrets/ checkout — fall back to OCI_USERNAME/OCIR_TOKEN/
# OCI_EMAIL already in the environment (CI/CD variables).
if [ -z "${OCI_USERNAME:-}" ] || [ -z "${OCIR_TOKEN:-}" ]; then
  # shellcheck disable=SC1091
  source "$SECRETS_DIR/registry.env"
fi
: "${OCI_USERNAME:?OCI_USERNAME not set}"
: "${OCIR_TOKEN:?OCIR_TOKEN not set}"
: "${OCI_EMAIL:?OCI_EMAIL not set}"
kubectl -n smoke create secret docker-registry ocir-pull \
  --docker-server="$(ocir_host)" --docker-username="$OCI_USERNAME" \
  --docker-password="$OCIR_TOKEN" --docker-email="$OCI_EMAIL" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n smoke create secret generic zebra-smoke-secrets \
  --from-literal=ORACLE_DSN="$E2E_PROVISIONER_DSN" \
  --from-literal=ORACLE_USERNAME="$SMOKE_SCHEMA" \
  --from-literal=ORACLE_PASSWORD="$E2E_SCHEMA_PASSWORD" \
  --from-literal=ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
  --from-literal=DJANGO_SECRET_KEY="$DJANGO_SECRET_KEY" \
  --from-literal=SMOKE_PASSWORD="$SMOKE_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -

log "deploying smoke instance at $WEB:$TAG"
( cd "$K8S_DIR/overlays/smoke" && kustomize edit set image "zebra-web=$WEB:$TAG" )
kustomize build "$K8S_DIR/overlays/smoke" | kubectl apply -f -
git -C "$OKE_DIR" checkout -- k8s/overlays/smoke 2>/dev/null || true

kubectl -n smoke rollout status deploy/zebra-web --timeout=180s

log "provisioning smoke user"
POD="$(kubectl -n smoke get pod -l app=zebra-web -o jsonpath='{.items[0].metadata.name}')"
# SMOKE_PASSWORD is already in the pod env (from zebra-smoke-secrets); create the
# user via a shell one-liner (matches the proven deploy path — no custom command).
kubectl -n smoke exec "$POD" -- python zebra-agent-web/manage.py shell -c \
  "import os; from django.contrib.auth.models import User; u,_=User.objects.get_or_create(username='smoke'); u.set_password(os.environ['SMOKE_PASSWORD']); u.save(); print('smoke user ready')"

log "port-forwarding smoke service → localhost:18000"
kubectl -n smoke port-forward svc/zebra-web 18000:80 >/dev/null 2>&1 &
PF_PID=$!
timeout 60 sh -c 'until curl -sf http://localhost:18000/api/health/ >/dev/null; do sleep 2; done'

log "running smoke suite"
( cd "$PROJECT_ROOT" \
  && SMOKE_BASE_URL="http://localhost:18000" SMOKE_USERNAME="smoke" SMOKE_PASSWORD="$SMOKE_PASSWORD" \
     uv run pytest zebra-agent-web/tests/smoke/ -v -m smoke )

log "smoke passed."
