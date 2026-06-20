#!/usr/bin/env bash
# Deploy the Tailscale subnet router so the cluster's services/pods are reachable
# privately over the tailnet (no public LB).
#
# Usage: TS_AUTHKEY=tskey-auth-xxxx 70-tailscale.sh
# Get a key: Tailscale admin → Settings → Keys → Generate auth key (reusable,
# optionally pre-approved & tagged). Approve the advertised routes in the admin
# console (Machines → zebra-oke → Edit route settings) once it connects.
set -euo pipefail
source "$(dirname "$0")/lib.sh"
require kubectl

: "${TS_AUTHKEY:?set TS_AUTHKEY (tskey-auth-...)}"

kubectl apply -f "$K8S_DIR/base/tailscale/namespace.yaml"
kubectl -n tailscale create secret generic tailscale-auth \
  --from-literal=TS_AUTHKEY="$TS_AUTHKEY" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -k "$K8S_DIR/base/tailscale"
kubectl -n tailscale rollout status deploy/tailscale-subnet-router --timeout=120s

log "subnet router up. In the Tailscale admin console:"
log "  1) approve advertised routes 10.96.0.0/16 + 10.244.0.0/16 for host 'zebra-oke'"
log "  2) then from any tailnet device:  curl http://<prod-clusterIP>/api/health/"
log "Find the prod ClusterIP:  kubectl -n prod get svc zebra-web -o jsonpath='{.spec.clusterIP}'"
