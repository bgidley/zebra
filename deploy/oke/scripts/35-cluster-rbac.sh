#!/usr/bin/env bash
# Apply the in-pod agents' identity + RBAC (claude-code / mac-claude SAs and their
# Role/ClusterRole bindings, incl. cross-namespace edit). Idempotent (apply-style).
#
# PRIVILEGED, OPERATOR-ONLY: run this with the cluster-admin kubeconfig (the one
# produced by 20-kubeconfig.sh). It is deliberately NOT part of the CI deploy
# (40-deploy.sh / oke_deploy): the CI runner (ci:gitlab-runner, ClusterRole
# oke-ci-deployer) is scoped to workloads and has no rbac.authorization.k8s.io
# verbs, so it cannot — and must not — reconcile these objects.
#
# Run order during bootstrap: 30-create-secrets.sh -> 35-cluster-rbac.sh -> 40-deploy.sh
# (the SAs must exist before the workloads that reference them are deployed).
set -euo pipefail
source "$(dirname "$0")/lib.sh"
require kubectl
require kustomize

log "applying cluster RBAC (claude-code + mac-claude identity & bindings)"
kustomize build "$K8S_DIR/cluster-rbac" | kubectl apply -f -
log "cluster RBAC applied."
