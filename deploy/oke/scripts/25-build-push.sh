#!/usr/bin/env bash
# Build the web (+ optionally claude) image with buildah and push to OCIR.
# Usage: 25-build-push.sh [tag]   (tag defaults to the short git SHA)
# Env:   BUILD_CLAUDE=1 to also build/push the claude-code image.
set -euo pipefail
source "$(dirname "$0")/lib.sh"
require buildah
require git

PROJECT_ROOT="$(cd "$OKE_DIR/../.." && pwd)"
TAG="${1:-$(git -C "$PROJECT_ROOT" rev-parse --short HEAD)}"
REGISTRY="$(tf_out ocir_registry)"
WEB_IMG="$REGISTRY/${OCIR_REPO_PREFIX:-zebra}/zebra-web"
CLAUDE_IMG="$REGISTRY/${OCIR_REPO_PREFIX:-zebra}/zebra-claude"

ocir_login buildah

log "baking version.json"
( cd "$PROJECT_ROOT" && uv run python scripts/gen_version.py > version.json )

log "building $WEB_IMG:$TAG"
buildah bud -f "$PROJECT_ROOT/Dockerfile" -t "$WEB_IMG:$TAG" -t "$WEB_IMG:latest" "$PROJECT_ROOT"
buildah push "$WEB_IMG:$TAG"
buildah push "$WEB_IMG:latest"

if [ "${BUILD_CLAUDE:-0}" = "1" ]; then
  log "building $CLAUDE_IMG:$TAG"
  buildah bud -f "$PROJECT_ROOT/docker/claude/Dockerfile" -t "$CLAUDE_IMG:$TAG" -t "$CLAUDE_IMG:latest" "$PROJECT_ROOT"
  buildah push "$CLAUDE_IMG:$TAG"
  buildah push "$CLAUDE_IMG:latest"
fi

log "pushed tag: $TAG"
echo "$TAG"
