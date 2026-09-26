#!/usr/bin/env bash
# Expose Zebra on the internet via a Cloudflare Tunnel (F117). Idempotent.
#
#   deploy/podman/setup-tunnel.sh zebra.example.com
#
# Prereq (once, interactive): `cloudflared tunnel login` — writes ~/.cloudflared/cert.pem
# for the Cloudflare zone that owns the hostname.
#
# Creates (or reuses) the named tunnel, routes <hostname> DNS to it, writes
# /etc/cloudflared/config.yml sending only that hostname to 127.0.0.1:8000, and runs
# it as the system `cloudflared` service. The deploy script never touches this service.
set -euo pipefail

HOSTNAME_FQDN=${1:?usage: setup-tunnel.sh <hostname>}
TUNNEL_NAME="${TUNNEL_NAME:-zebra}"
ORIGIN="${ORIGIN:-http://127.0.0.1:8000}"

[ -f "$HOME/.cloudflared/cert.pem" ] || { echo "Run 'cloudflared tunnel login' first" >&2; exit 1; }

if ! cloudflared tunnel info "$TUNNEL_NAME" >/dev/null 2>&1; then
  cloudflared tunnel create "$TUNNEL_NAME"
fi
TUNNEL_ID=$(cloudflared tunnel list --output json | jq -r --arg n "$TUNNEL_NAME" '.[] | select(.name==$n) | .id')
[ -n "$TUNNEL_ID" ] || { echo "tunnel $TUNNEL_NAME not found" >&2; exit 1; }

cloudflared tunnel route dns --overwrite-dns "$TUNNEL_NAME" "$HOSTNAME_FQDN"

sudo install -d -m 755 /etc/cloudflared
sudo install -m 600 "$HOME/.cloudflared/$TUNNEL_ID.json" "/etc/cloudflared/$TUNNEL_ID.json"
sudo tee /etc/cloudflared/config.yml >/dev/null <<EOF
# Managed by deploy/podman/setup-tunnel.sh — re-run it rather than editing.
tunnel: $TUNNEL_ID
credentials-file: /etc/cloudflared/$TUNNEL_ID.json
ingress:
  - hostname: $HOSTNAME_FQDN
    service: $ORIGIN
  - service: http_status:404
EOF
cloudflared tunnel ingress validate --config /etc/cloudflared/config.yml

if ! systemctl list-unit-files cloudflared.service >/dev/null 2>&1 \
   || ! systemctl cat cloudflared.service >/dev/null 2>&1; then
  sudo cloudflared service install
fi
sudo systemctl enable cloudflared
sudo systemctl restart cloudflared
sleep 3
systemctl is-active cloudflared
echo "Tunnel $TUNNEL_NAME ($TUNNEL_ID) -> https://$HOSTNAME_FQDN -> $ORIGIN"
