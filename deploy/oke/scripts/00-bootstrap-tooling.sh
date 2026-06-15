#!/usr/bin/env bash
# Install the CLIs the migration needs (idempotent). Oracle Linux / aarch64.
# Safe to re-run: each tool is skipped if already present.
set -euo pipefail
source "$(dirname "$0")/lib.sh"

install_oci() {
  command -v oci >/dev/null 2>&1 && {
    log "oci CLI present: $(oci --version)"
    return
  }
  log "installing oci CLI…"
  bash -c "$(curl -fsSL https://raw.githubusercontent.com/oracle/oci-cli/master/scripts/install/install.sh)" -- --accept-all-defaults
}

install_kubectl() {
  command -v kubectl >/dev/null 2>&1 && {
    log "kubectl present"
    return
  }
  log "installing kubectl…"
  local ver
  ver="$(curl -fsSL https://dl.k8s.io/release/stable.txt)"
  curl -fsSLo /tmp/kubectl "https://dl.k8s.io/release/${ver}/bin/linux/arm64/kubectl"
  sudo install -m 0755 /tmp/kubectl /usr/local/bin/kubectl
}

install_terraform() {
  command -v terraform >/dev/null 2>&1 && {
    log "terraform present: $(terraform version | head -1)"
    return
  }
  log "installing terraform…"
  sudo dnf install -y dnf-plugins-core
  sudo dnf config-manager --add-repo https://rpm.releases.hashicorp.com/RHEL/hashicorp.repo
  sudo dnf install -y terraform
}

install_kustomize() {
  command -v kustomize >/dev/null 2>&1 && {
    log "kustomize present"
    return
  }
  # kubectl has kustomize built in (`kubectl kustomize`); install standalone too.
  log "installing kustomize…"
  curl -fsSL "https://raw.githubusercontent.com/kubernetes-sigs/kustomize/master/hack/install_kustomize.sh" | bash
  sudo install -m 0755 ./kustomize /usr/local/bin/kustomize && rm -f ./kustomize
}

install_buildah() {
  command -v buildah >/dev/null 2>&1 && {
    log "buildah present"
    return
  }
  log "installing buildah…"
  sudo dnf install -y buildah
}

install_oci
install_kubectl
install_terraform
install_kustomize
install_buildah
log "tooling ready."
