#!/usr/bin/env bash
# Generate a kubeconfig for the cluster and verify connectivity.
set -euo pipefail
source "$(dirname "$0")/lib.sh"
require oci
require kubectl

CLUSTER_ID="$(tf_out cluster_id)"
REGION="$(tf_out region)"
KUBECONFIG_PATH="${KUBECONFIG:-$HOME/.kube/config}"

mkdir -p "$(dirname "$KUBECONFIG_PATH")"
log "writing kubeconfig for cluster $CLUSTER_ID → $KUBECONFIG_PATH"
oci ce cluster create-kubeconfig \
  --cluster-id "$CLUSTER_ID" \
  --file "$KUBECONFIG_PATH" \
  --region "$REGION" \
  --token-version 2.0.0 \
  --kube-endpoint PUBLIC_ENDPOINT

log "nodes:"
kubectl get nodes -o wide
