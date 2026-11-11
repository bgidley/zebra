#!/usr/bin/env bash
# Expose Zebra on the internet via a Cloudflare Tunnel (F117). Idempotent.
#
#   deploy/podman/setup-tunnel.sh zebra.example.com
#   deploy/podman/setup-tunnel.sh --print-config zebra.example.com   # show config.yml, change nothing
#
# Prereq (once, interactive): `cloudflared tunnel login` — writes ~/.cloudflared/cert.pem
# for the Cloudflare zone that owns the hostname.
#
# Creates (or reuses) the named tunnel, routes <hostname> DNS to it, writes
# /etc/cloudflared/config.yml and runs it as the system `cloudflared` service. The deploy
# script never touches this service. The config sends <hostname> to 127.0.0.1:8000, except:
#
#   wss://<hostname>/relay/commons -> 127.0.0.1:7779  public Commons relay (#231), if installed
#   wss://<hostname>/relay/sync    -> 127.0.0.1:7778  private sync relay (#246), if installed
#
# A relay counts as installed when its Quadlet is in ~/.config/containers/systemd/ (the
# runbooks put it there), so re-running this script keeps its route. Override with
# ROUTE_COMMONS=1|0 and ROUTE_SYNC=1|0. Both paths are exact and live under /relay/, where
# the web app has no pages: if Cloudflare Access protects the hostname, one Access app for
# <hostname>/relay with a Bypass policy opens the relays to other Zebras, while every web page
# (/commons/ included) stays behind Access.
set -euo pipefail

PRINT_ONLY=0
if [ "${1:-}" = "--print-config" ]; then
  PRINT_ONLY=1
  shift
fi
HOSTNAME_FQDN=${1:?usage: setup-tunnel.sh [--print-config] <hostname>}
TUNNEL_NAME="${TUNNEL_NAME:-zebra}"
ORIGIN="${ORIGIN:-http://127.0.0.1:8000}"
QUADLET_DIR="${QUADLET_DIR:-$HOME/.config/containers/systemd}"
COMMONS_ORIGIN="${COMMONS_ORIGIN:-http://127.0.0.1:7779}"
SYNC_ORIGIN="${SYNC_ORIGIN:-http://127.0.0.1:7778}"

# route_wanted <override> <quadlet file>: 1 if the relay's route belongs in the config.
route_wanted() {
  case "$1" in
    1) echo 1 ;;
    0) echo 0 ;;
    "") if [ -f "$QUADLET_DIR/$2" ]; then echo 1; else echo 0; fi ;;
    *) echo "expected 1 or 0, got '$1'" >&2; return 1 ;;
  esac
}
ROUTE_COMMONS=$(route_wanted "${ROUTE_COMMONS:-}" zebra-commons-relay.container)
ROUTE_SYNC=$(route_wanted "${ROUTE_SYNC:-}" zebra-sync-relay.container)

# render_config <tunnel id>: the whole config.yml. Relay paths come before the hostname rule,
# because cloudflared uses the first rule that matches.
render_config() {
  echo "# Managed by deploy/podman/setup-tunnel.sh — re-run it rather than editing."
  echo "tunnel: $1"
  echo "credentials-file: /etc/cloudflared/$1.json"
  echo "ingress:"
  if [ "$ROUTE_COMMONS" = 1 ]; then
    printf '  - hostname: %s\n    path: ^/relay/commons$\n    service: %s\n' \
      "$HOSTNAME_FQDN" "$COMMONS_ORIGIN"
  fi
  if [ "$ROUTE_SYNC" = 1 ]; then
    printf '  - hostname: %s\n    path: ^/relay/sync$\n    service: %s\n' "$HOSTNAME_FQDN" "$SYNC_ORIGIN"
  fi
  printf '  - hostname: %s\n    service: %s\n' "$HOSTNAME_FQDN" "$ORIGIN"
  echo "  - service: http_status:404"
}

if [ "$PRINT_ONLY" = 1 ]; then
  render_config "${TUNNEL_ID:-<tunnel-id>}"
  exit 0
fi

[ -f "$HOME/.cloudflared/cert.pem" ] || { echo "Run 'cloudflared tunnel login' first" >&2; exit 1; }

if ! cloudflared tunnel info "$TUNNEL_NAME" >/dev/null 2>&1; then
  cloudflared tunnel create "$TUNNEL_NAME"
fi
TUNNEL_ID=$(cloudflared tunnel list --output json | jq -r --arg n "$TUNNEL_NAME" '.[] | select(.name==$n) | .id')
[ -n "$TUNNEL_ID" ] || { echo "tunnel $TUNNEL_NAME not found" >&2; exit 1; }

cloudflared tunnel route dns --overwrite-dns "$TUNNEL_NAME" "$HOSTNAME_FQDN"

sudo install -d -m 755 /etc/cloudflared
sudo install -m 600 "$HOME/.cloudflared/$TUNNEL_ID.json" "/etc/cloudflared/$TUNNEL_ID.json"
render_config "$TUNNEL_ID" | sudo tee /etc/cloudflared/config.yml >/dev/null
sudo cloudflared tunnel --config /etc/cloudflared/config.yml ingress validate

# A token-based unit (dashboard-managed tunnel) ignores config.yml — replace it.
if systemctl cat cloudflared.service 2>/dev/null | grep -q -- '--token'; then
  sudo systemctl stop cloudflared || true
  sudo cloudflared service uninstall
fi
if ! systemctl cat cloudflared.service >/dev/null 2>&1; then
  sudo cloudflared service install
fi
sudo systemctl enable cloudflared
sudo systemctl restart cloudflared
sleep 3
systemctl is-active cloudflared
echo "Tunnel $TUNNEL_NAME ($TUNNEL_ID) -> https://$HOSTNAME_FQDN -> $ORIGIN"
if [ "$ROUTE_COMMONS" = 1 ]; then echo "  wss://$HOSTNAME_FQDN/relay/commons -> $COMMONS_ORIGIN"; fi
if [ "$ROUTE_SYNC" = 1 ]; then echo "  wss://$HOSTNAME_FQDN/relay/sync -> $SYNC_ORIGIN"; fi
