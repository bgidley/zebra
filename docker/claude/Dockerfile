# ============================================================================
# Claude Code sandbox image — interactive Claude Code CLI + autonomous Zebra
# agent + dev toolchain. Long-lived pod; the repo lives on a PVC at /workspace.
# Built for arm64 (Ampere A1 / OKE).
# ============================================================================
FROM python:3.14-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PATH="/root/.local/bin:${PATH}"

# Base tooling. buildah + fuse-overlayfs + netavark/aardvark-dns + nftables + crun:
# this image doubles as the in-cluster GitLab Runner's build container
# (deploy/oke/scripts/25-build-push.sh) — buildah needs a network backend (netavark,
# which itself shells out to `nft`) and an OCI runtime to run RUN steps, none of
# which are pulled in by --no-install-recommends (only Recommends of buildah's deps).
RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates openssh-client ripgrep jq less unzip gnupg \
        buildah fuse-overlayfs netavark aardvark-dns nftables crun \
    && rm -rf /var/lib/apt/lists/*

# uv (Python package/exec manager used across the monorepo)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Node.js 22 + Claude Code CLI
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && rm -rf /var/lib/apt/lists/*

# kubectl (arm64) — in-cluster access uses the mounted ServiceAccount token
RUN KVER="$(curl -fsSL https://dl.k8s.io/release/stable.txt)" \
    && curl -fsSLo /usr/local/bin/kubectl "https://dl.k8s.io/release/${KVER}/bin/linux/arm64/kubectl" \
    && chmod +x /usr/local/bin/kubectl

# glab (GitLab CLI) + gh (GitHub CLI), arm64 — required, fetched dynamically.
RUN arch=arm64; \
    GLAB_VER="$(curl -fsSL 'https://gitlab.com/api/v4/projects/gitlab-org%2Fcli/releases' | jq -r '.[0].tag_name' | sed 's/^v//')" \
    && curl -fsSL "https://gitlab.com/gitlab-org/cli/-/releases/v${GLAB_VER}/downloads/glab_${GLAB_VER}_linux_${arch}.tar.gz" \
        | tar -xz -C /tmp \
    && install -m0755 /tmp/bin/glab /usr/local/bin/glab \
    && rm -rf /tmp/* \
    && glab --version \
    && GH_VER=2.62.0 \
    && curl -fsSL "https://github.com/cli/cli/releases/download/v${GH_VER}/gh_${GH_VER}_linux_${arch}.tar.gz" \
        | tar -xz -C /tmp \
    && install -m0755 "/tmp/gh_${GH_VER}_linux_${arch}/bin/gh" /usr/local/bin/gh \
    && rm -rf "/tmp/gh_${GH_VER}_linux_${arch}" \
    && gh --version

WORKDIR /workspace

# Repo is bind-mounted/PVC-mounted at runtime; nothing is baked in.
# Default command is set by the Deployment (sleep infinity); exec in with:
#   kubectl -n tools exec -it deploy/claude-code -- claude
CMD ["bash"]
