# ============================================================================
# Claude Code sandbox image — interactive Claude Code CLI + autonomous Zebra
# agent + dev toolchain. Long-lived pod; the repo lives on a PVC at /workspace.
# Built for arm64 (Ampere A1 / OKE).
# ============================================================================
FROM python:3.14-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PATH="/root/.local/bin:${PATH}"

# Base tooling
RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates openssh-client ripgrep jq less unzip gnupg \
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

# glab (GitLab CLI) + gh (GitHub CLI), arm64
RUN GLAB_VER="1.45.0" \
    && curl -fsSL "https://gitlab.com/gitlab-org/cli/-/releases/v${GLAB_VER}/downloads/glab_${GLAB_VER}_linux_arm64.tar.gz" \
       | tar -xz -C /usr/local --strip-components=1 bin/glab \
    && GH_VER="2.62.0" \
    && curl -fsSL "https://github.com/cli/cli/releases/download/v${GH_VER}/gh_${GH_VER}_linux_arm64.tar.gz" \
       | tar -xz -C /tmp \
    && install -m0755 "/tmp/gh_${GH_VER}_linux_arm64/bin/gh" /usr/local/bin/gh \
    && rm -rf /tmp/gh_*

WORKDIR /workspace

# Repo is bind-mounted/PVC-mounted at runtime; nothing is baked in.
# Default command is set by the Deployment (sleep infinity); exec in with:
#   kubectl -n tools exec -it deploy/claude-code -- claude
CMD ["bash"]
