#!/usr/bin/env bash
# Deploy the Tailscale subnet router so the cluster's services/pods are reachable
# privately over the tailnet (no public LB).
#
# *** NEVER apply deploy/oke/k8s/base/tailscale/ with raw kubectl — the image
# *** field contains a REGISTRY placeholder that only this script substitutes.
# *** Raw apply → ImagePullBackOff and loss of Tailscale cluster connectivity.
#
# Usage:
#   Auth key:    TS_AUTHKEY=tskey-auth-xxxx                70-tailscale.sh
#   OAuth (rec): TS_AUTHKEY=tskey-client-xxxx TS_TAG=tag:zebra 70-tailscale.sh
#
# An OAuth client secret (tskey-client-...) is preferred for permanent infra: it
# does not expire and the node it creates is TAGGED (tagged nodes never expire).
# OAuth REQUIRES a tag, so set TS_TAG to a tag in your ACL tagOwners scoped to the
# client. A plain auth key (tskey-auth-...) works too but expires in <=90 days.
# Add the tag to the ACL `autoApprovers.routes` to skip manual route approval.
#
# State note: tailscale persists node identity + serve config in the tailscale-state
# Secret. Changing TS_EXTRA_ARGS (especially --advertise-tags) without deleting that
# Secret will cause "tailscale up requires --reset" on the next pod start. If that
# happens: kubectl -n tailscale delete secret tailscale-state && re-run this script.
set -euo pipefail
source "$(dirname "$0")/lib.sh"
require kubectl

: "${TS_AUTHKEY:?set TS_AUTHKEY (tskey-client-... for OAuth, or tskey-auth-...)}"
TS_TAG="${TS_TAG:-}"
case "$TS_AUTHKEY" in
  tskey-client-*) [ -n "$TS_TAG" ] || die "OAuth secret needs a tag — set TS_TAG (e.g. tag:zebra)" ;;
esac

EXTRA_ARGS="--hostname=zebra-oke --accept-dns=false"
[ -n "$TS_TAG" ] && EXTRA_ARGS="$EXTRA_ARGS --advertise-tags=$TS_TAG"

kubectl apply -f "$K8S_DIR/base/tailscale/namespace.yaml"
kubectl -n tailscale create secret generic tailscale-auth \
  --from-literal=TS_AUTHKEY="$TS_AUTHKEY" \
  --dry-run=client -o yaml | kubectl apply -f -

# OCIR pull secret (the tailscale image is mirrored into OCIR).
# shellcheck disable=SC1091
source "$SECRETS_DIR/registry.env"
kubectl -n tailscale create secret docker-registry ocir-pull \
  --docker-server="$(ocir_host)" --docker-username="$OCI_USERNAME" \
  --docker-password="$OCIR_TOKEN" --docker-email="$OCI_EMAIL" \
  --dry-run=client -o yaml | kubectl apply -f -

# Pin the OCIR registry into the image reference, then apply.
REGISTRY="$(tf_out ocir_registry)"
( cd "$K8S_DIR/base/tailscale" \
  && kustomize edit set image "REGISTRY/zebra/tailscale=${REGISTRY}/zebra/tailscale:stable" 2>/dev/null \
  || true )
kubectl apply -k "$K8S_DIR/base/tailscale"
( cd "$K8S_DIR/base/tailscale" && git checkout -- kustomization.yaml 2>/dev/null || true )
# Inject the (possibly tag-bearing) extra args; the manifest default is overridden here.
kubectl -n tailscale set env deploy/tailscale-subnet-router TS_EXTRA_ARGS="$EXTRA_ARGS"
kubectl -n tailscale rollout status deploy/tailscale-subnet-router --timeout=120s

log "subnet router up (tag: ${TS_TAG:-none}). Access:"
log "  HTTPS (passkeys): https://zebra-oke.tailf1e473.ts.net/"
log "  ClusterIP (HTTP): http://$(kubectl -n prod get svc zebra-web -o jsonpath='{.spec.clusterIP}')/"
log "If routes need approval, go to the Tailscale admin console → zebra-oke → approve routes."
