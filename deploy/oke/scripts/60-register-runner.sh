#!/usr/bin/env bash
# Register the in-cluster GitLab Runner and create its token secret.
#
# Modern GitLab uses *runner authentication tokens* (glrt-...). Create the runner
# record once in the GitLab UI/API (Project → Settings → CI/CD → Runners → New
# project runner; tags: oke-k8s), then pass its token here.
#
# Usage: GITLAB_RUNNER_TOKEN=glrt-xxx [GITLAB_URL=https://gitlab.com] 60-register-runner.sh
set -euo pipefail
source "$(dirname "$0")/lib.sh"
require kubectl

: "${GITLAB_RUNNER_TOKEN:?set GITLAB_RUNNER_TOKEN (glrt-... authentication token)}"
GITLAB_URL="${GITLAB_URL:-https://gitlab.com}"

kubectl create namespace ci --dry-run=client -o yaml | kubectl apply -f -

# Token + URL consumed by the runner Deployment (envFrom) at startup.
kubectl -n ci create secret generic gitlab-runner-secret \
  --from-literal=runner-token="$GITLAB_RUNNER_TOKEN" \
  --from-literal=ci-server-url="$GITLAB_URL" \
  --dry-run=client -o yaml | kubectl apply -f -

log "gitlab-runner-secret created in ns ci."
log "Apply the runner manifests:  kubectl apply -k $K8S_DIR/base/gitlab-runner"
log "Then verify it shows online under the project's CI/CD → Runners."
