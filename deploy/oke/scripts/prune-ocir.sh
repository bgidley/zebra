#!/usr/bin/env bash
# Keep only the most recent N images in each OCIR repo (registry hygiene — the
# replacement for the old host-disk pruning). Run from the oke_deploy CI stage.
# Env: KEEP (default 5).
set -euo pipefail
source "$(dirname "$0")/lib.sh"
require oci

KEEP="${KEEP:-5}"
COMPARTMENT="$(tf_out compartment_ocid)"
PREFIX="${OCIR_REPO_PREFIX:-zebra}"

for repo in "$PREFIX/zebra-web" "$PREFIX/zebra-claude"; do
  log "pruning $repo (keeping newest $KEEP)"
  # Newest first; slice off the first KEEP, delete the rest.
  ids="$(oci artifacts container image list \
            --compartment-id "$COMPARTMENT" \
            --repository-name "$repo" \
            --sort-by TIMECREATED --sort-order DESC --all \
            --query "data.items[${KEEP}:].id" --raw-output 2>/dev/null \
          | tr -d '[],"' || true)"
  for id in $ids; do
    [ -n "$id" ] || continue
    log "deleting image $id"
    oci artifacts container image delete --image-id "$id" --force >/dev/null
  done
done
log "OCIR prune complete."
