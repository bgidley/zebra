#!/usr/bin/env bash
# Check the OCI Resource Manager stack (deploy/oci) without OCI credentials (#279).
#
#   0. self-test: fmt -check must reject tests/iac/fixtures/misformatted (#299)
#   1. terraform fmt -check (prints the diff on failure), init, validate
#   2. terraform test        (deploy/oci/tests, mocked oci provider)
#   3. terraform plan + show -json with throwaway credentials, then
#      scripts/oci_plan_scan.py checks the plan against deploy/oci/free_tier_allowlist.yaml
#
# The plan makes no OCI API calls: every lookup in the stack is keyed on the compartment the
# stack creates, so it is deferred to apply. The throwaway key never leaves the temp dir.
#
# Terraform runs in a pinned container (no host install). Never runs apply.
#
# Usage: scripts/oci_iac_check.sh [--keep-plan <path>]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="${TERRAFORM_IMAGE:-docker.io/hashicorp/terraform:1.12.2}"
PLUGINS="${TF_PLUGIN_CACHE:-$HOME/.cache/zebra-terraform-plugins}"
KEEP_PLAN=""
if [ "${1:-}" = "--keep-plan" ]; then
  KEEP_PLAN="${2:?--keep-plan needs a path}"
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$PLUGINS" "$WORK/oci"
# Work on a copy so .terraform/ and plan files never land in the checkout.
cp -r "$ROOT/deploy/oci" "$WORK/stack"

# Throwaway API key and OCIDs: enough for the provider to configure, never valid anywhere.
FAKE_TENANCY="ocid1.tenancy.oc1..aaaaaaaazebraplanscanzebraplanscanzebraplanscanzebrapla"
openssl genrsa -out "$WORK/oci/key.pem" 2048 2>/dev/null
FINGERPRINT="$(openssl rsa -in "$WORK/oci/key.pem" -pubout -outform DER 2>/dev/null \
  | openssl md5 -c | awk '{print $NF}')"
cat >"$WORK/oci/config" <<EOF
[DEFAULT]
user=ocid1.user.oc1..aaaaaaaazebraplanscanzebraplanscanzebraplanscanzebraplanscanze
fingerprint=$FINGERPRINT
tenancy=$FAKE_TENANCY
region=uk-london-1
key_file=/root/.oci/key.pem
EOF

tf() {
  podman run --rm \
    -v "$WORK/stack:/stack:Z" \
    -v "$WORK/oci:/root/.oci:Z" \
    -v "$PLUGINS:/plugins:z" \
    -e TF_PLUGIN_CACHE_DIR=/plugins \
    -e TF_IN_AUTOMATION=1 \
    -e TF_VAR_tenancy_ocid="$FAKE_TENANCY" \
    -e TF_VAR_compartment_ocid="$FAKE_TENANCY" \
    -w /stack "$IMAGE" "$@"
}

# terraform fmt aligns `=` only within a run of consecutive single-line attributes; a blank line,
# comment line or nested block starts a new run, so differently aligned groups are correct.
fmt_check() { # $1: directory under $WORK; prints the diff, exits non-zero when unformatted
  podman run --rm -v "$WORK/$1:/fmt:Z" -w /fmt "$IMAGE" fmt -check -recursive -diff -no-color
}

echo "== terraform fmt self-test (a mis-formatted file must fail)"
cp -r "$ROOT/tests/iac/fixtures/misformatted" "$WORK/misformatted"
if fmt_check misformatted >"$WORK/fmt-selftest.diff" 2>&1; then
  echo "FAIL: terraform fmt -check passed a mis-formatted file; the fmt gate is not checking"
  exit 1
fi
if ! grep -q '^[-+] ' "$WORK/fmt-selftest.diff"; then
  echo "FAIL: terraform fmt -check rejected the fixture but printed no diff:"
  cat "$WORK/fmt-selftest.diff"
  exit 1
fi
echo "ok: rejected, with a diff"

echo "== terraform fmt"
if ! fmt_check stack >"$WORK/fmt.diff" 2>&1; then
  cat "$WORK/fmt.diff"
  echo "FAIL: deploy/oci is not terraform fmt clean; apply the diff above (terraform fmt -recursive)"
  exit 1
fi
echo "ok: clean"
echo "== terraform init"
tf init -input=false -backend=false -lockfile=readonly -no-color >/dev/null
echo "== terraform validate"
tf validate -no-color
echo "== terraform test (mocked oci provider)"
tf test -no-color
echo "== terraform plan (throwaway credentials, no API calls)"
tf plan -input=false -refresh=false -lock=false -no-color -out=/stack/ci.tfplan >/dev/null
tf show -json /stack/ci.tfplan >"$WORK/plan.json"
if [ -n "$KEEP_PLAN" ]; then
  cp "$WORK/plan.json" "$KEEP_PLAN"
fi
echo "== Always Free plan scan"
uv run python "$ROOT/scripts/oci_plan_scan.py" "$WORK/plan.json" \
  --allowlist "$ROOT/deploy/oci/free_tier_allowlist.yaml"
