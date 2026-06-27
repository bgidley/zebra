#!/usr/bin/env bash
# Deploy/promote the long-lived workloads (prod web+daemon, claude-code) at a
# given image tag. Usage: 40-deploy.sh <tag>
#
# Note: the web/daemon images are built per-commit (tag = git SHA), but the
# claude-code image is a source-independent runtime sandbox (docker/claude/
# Dockerfile — "nothing is baked in"; the repo is PVC-mounted at runtime). It is
# only built when BUILD_CLAUDE=1, so it is NOT published per-SHA. We therefore
# pin claude-code to CLAUDE_TAG (default "latest") rather than the web SHA —
# pinning it to <sha> caused ImagePullBackOff (manifest unknown). Override with
# CLAUDE_TAG=<tag> if you build the claude image at a specific tag.
set -euo pipefail
source "$(dirname "$0")/lib.sh"
require kubectl
require kustomize

TAG="${1:?usage: 40-deploy.sh <image-tag>}"
CLAUDE_TAG="${CLAUDE_TAG:-latest}"
REGISTRY="$(tf_out ocir_registry)"
PREFIX="${OCIR_REPO_PREFIX:-zebra}"
WEB="$REGISTRY/$PREFIX/zebra-web"
CLAUDE="$REGISTRY/$PREFIX/zebra-claude"

# Pin images in the kustomizations (no edits committed — done in a temp render).
render() {
  local dir="$1"
  ( cd "$dir" \
    && kustomize edit set image "zebra-web=$WEB:$TAG" 2>/dev/null || true
    cd "$dir" \
    && kustomize edit set image "zebra-claude=$CLAUDE:$CLAUDE_TAG" 2>/dev/null || true )
}
render "$K8S_DIR/base/prod-web"
render "$K8S_DIR/base/prod-daemon"
render "$K8S_DIR/base/claude-code"

log "applying base workloads at tag $TAG"
kustomize build "$K8S_DIR/base" | kubectl apply -f -

log "waiting for rollouts…"
kubectl -n prod rollout status deploy/zebra-web --timeout=180s
kubectl -n prod rollout status deploy/zebra-daemon --timeout=120s
kubectl -n tools rollout status deploy/claude-code --timeout=120s

# Restore placeholder so we don't commit a pinned SHA into the kustomization.
git -C "$OKE_DIR" checkout -- k8s 2>/dev/null || true
log "deploy complete."
