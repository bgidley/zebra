#!/usr/bin/env bash
# One-shot, idempotent bootstrap for the single Zebra host (Oracle Linux 9, OCI A1).
#
# Installs everything the GitLab shell runner and the rootless-Podman deploy need:
#   - grows the root filesystem to fill the boot volume
#   - uv (for opc)
#   - gitlab-runner, running jobs as opc (not the gitlab-runner user), concurrency 1
#   - systemd linger for opc so user units (Quadlet containers) run without a login
#   - cloudflared (package only; tunnel setup is deploy/podman/setup-tunnel.sh)
#
# Usage (as opc, which has sudo):
#   deploy/podman/bootstrap-host.sh                       # install / repair
#   RUNNER_TOKEN=glrt-... deploy/podman/bootstrap-host.sh # also register the runner
set -euo pipefail

RUN_USER="${RUN_USER:-opc}"
RUNNER_DESC="${RUNNER_DESC:-$(hostname -s)-podman}"

log() { printf '\n== %s\n' "$*"; }

log "Grow root filesystem"
if [ -x /usr/libexec/oci-growfs ]; then
  sudo /usr/libexec/oci-growfs -y || echo "oci-growfs: nothing to grow"
fi
df -h /

log "Base packages"
sudo dnf install -y -q podman git curl jq openssl

log "uv"
if ! command -v uv >/dev/null && [ ! -x "$HOME/.local/bin/uv" ]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
"$HOME/.local/bin/uv" --version

log "gitlab-runner"
if ! command -v gitlab-runner >/dev/null; then
  curl -Ls https://packages.gitlab.com/install/repositories/runner/gitlab-runner/script.rpm.sh | sudo bash
  sudo dnf install -y -q gitlab-runner
fi
# Run jobs as $RUN_USER so they share its rootless Podman, uv cache and systemd user manager.
if ! grep -qE -- "--user\"? \"?$RUN_USER\"?" /etc/systemd/system/gitlab-runner.service 2>/dev/null; then
  sudo gitlab-runner stop || true
  sudo gitlab-runner uninstall || true
  sudo gitlab-runner install --user "$RUN_USER" --working-directory "/home/$RUN_USER" \
    --config /etc/gitlab-runner/config.toml
fi
# One job at a time: this box is 2 OCPU / 10 GB and also hosts prod + the agent.
sudo touch /etc/gitlab-runner/config.toml
if sudo grep -q '^concurrent' /etc/gitlab-runner/config.toml; then
  sudo sed -i 's/^concurrent.*/concurrent = 1/' /etc/gitlab-runner/config.toml
else
  sudo sed -i '1i concurrent = 1' /etc/gitlab-runner/config.toml
fi

if [ -n "${RUNNER_TOKEN:-}" ]; then
  if sudo grep -q "name = \"$RUNNER_DESC\"" /etc/gitlab-runner/config.toml; then
    echo "runner '$RUNNER_DESC' already registered — skipping"
  else
    sudo gitlab-runner register --non-interactive \
      --url https://gitlab.com --token "$RUNNER_TOKEN" \
      --executor shell --name "$RUNNER_DESC"
  fi
fi
sudo systemctl enable --now gitlab-runner
sudo systemctl restart gitlab-runner

log "Linger for $RUN_USER (user units survive logout / start at boot)"
sudo loginctl enable-linger "$RUN_USER"

log "cloudflared"
if ! command -v cloudflared >/dev/null; then
  sudo dnf config-manager --add-repo https://pkg.cloudflare.com/cloudflared-ascii.repo
  sudo dnf install -y -q cloudflared
fi

log "Zebra config dir"
install -d -m 700 "$HOME/.config/zebra" "$HOME/.config/containers/systemd"
if [ ! -f "$HOME/.config/zebra/site.env" ]; then
  install -m 600 "$(dirname "$0")/site.env.example" "$HOME/.config/zebra/site.env"
  echo "Created ~/.config/zebra/site.env from template — review it"
fi

log "Done"
cat <<EOF
Next steps (manual, once):
  cloudflared tunnel login                       # interactive: pick the Cloudflare zone
  deploy/podman/setup-tunnel.sh <hostname>       # e.g. zebra.example.com
  edit ~/.config/zebra/site.env                  # set the WebAuthn/CSRF origin to <hostname>
Then push to master: the deploy job writes ~/.config/zebra/prod.env from GitLab CI
variables, installs the Quadlet units and starts zebra-web + zebra-daemon.
EOF
