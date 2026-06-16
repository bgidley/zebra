#!/usr/bin/env bash
# Configure & verify OCI API auth. See docs/oci-onboarding.md for obtaining the inputs.
set -euo pipefail
source "$(dirname "$0")/lib.sh"
require oci

if [ ! -f "$HOME/.oci/config" ]; then
  log "no ~/.oci/config — launching interactive setup…"
  log "have ready: tenancy OCID, user OCID, region. It will generate an API key for you."
  oci setup config
  warn "Upload the generated public key (~/.oci/oci_api_key_public.pem) to your OCI user:"
  warn "  Console → Identity → Users → <you> → API Keys → Add API Key → Paste public key."
else
  log "~/.oci/config already present."
fi

log "verifying credentials (listing regions)…"
oci iam region list --query 'data[0].name' --raw-output >/dev/null \
  && log "OCI auth OK." \
  || die "OCI auth failed — check ~/.oci/config and that the public key is uploaded."
